import pytest
from pycloudlib.cloud import ImageType

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE
from tests.integration_tests.util import verify_clean_log


def _check_for_eject_errors(
    instance: IntegrationInstance,
):
    assert "sr0" not in instance.execute("mount")
    log = instance.read_from_file("/var/log/cloud-init.log")
    assert "Failed ejecting the provisioning iso" not in log
    verify_clean_log(log)


@pytest.mark.skipif(PLATFORM != "azure", reason="Test is Azure specific")
def test_azure_eject(session_cloud: IntegrationCloud):
    """Integration test for GitHub #4732.

    Azure uses `eject` but that is not always available on minimal images.
    Ensure udev's eject can be used on systemd-enabled systems.
    """
    with session_cloud.launch(
        launch_kwargs={
            "image_id": session_cloud.cloud_instance.daily_image(
                CURRENT_RELEASE.series, image_type=ImageType.MINIMAL
            )
        }
    ) as instance:
        source = get_validated_source(session_cloud)
        if source.installs_new_version():
            instance.install_new_cloud_init(source, clean=True)
            snapshot_id = instance.snapshot()
            try:
                with session_cloud.launch(
                    launch_kwargs={
                        "image_id": snapshot_id,
                    }
                ) as snapshot_instance:
                    _check_for_eject_errors(snapshot_instance)
            finally:
                session_cloud.cloud_instance.delete_image(snapshot_id)
        else:
            _check_for_eject_errors(instance)
