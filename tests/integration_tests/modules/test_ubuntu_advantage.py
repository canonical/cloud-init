import os

import pytest
from pycloudlib.cloud import ImageType

from tests.integration_tests.clouds import ImageSpecification, IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

CLOUD_INIT_UA_TOKEN = os.environ.get("CLOUD_INIT_UA_TOKEN")

ATTACH_FALLBACK = """\
#cloud-config
ubuntu_advantage:
  features:
    disable_auto_attach: true
  token: {token}
"""

UA_DAILY = """\
#cloud-config
apt:
  sources:
    ua-daily:
      source: 'ppa:ua-client/daily'
package_update: true
package_upgrade: true
packages:
- ubuntu-advantage-tools
"""

AUTO_ATTACH_CUSTOM_SERVICES = """\
#cloud-config
ubuntu_advantage:
  enable:
  - esm
  enable_beta:
  - realtime-kernel
"""


def did_ua_service_noop(client: IntegrationInstance) -> bool:
    ua_log = client.read_from_file("/var/log/ubuntu-advantage.log")
    return (
        "Skipping auto-attach and deferring to cloud-init to setup and"
        " configure auto-attach" in ua_log
    )


def is_auto_attached(client: IntegrationInstance) -> bool:
    return (
        "machine is attached to an Ubuntu Pro subscription."
        in client.execute("pro status").stdout
    )


@pytest.mark.adhoc
@pytest.mark.ubuntu
class TestUbuntuAdvantage:
    @pytest.mark.user_data(ATTACH_FALLBACK.format(token=CLOUD_INIT_UA_TOKEN))
    def test_valid_token(self, client: IntegrationInstance):
        assert CLOUD_INIT_UA_TOKEN, "CLOUD_INIT_UA_TOKEN env var not provided"
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        status = client.execute("ua status")
        assert status.ok
        assert "This machine is not attached" not in status.stdout


def install_ua_daily(session_cloud: IntegrationCloud):
    """Install `ubuntu-advantage-tools` from ppa:ua-client/daily in an
    Ubuntu Pro image.

    TODO: Remove this after UA releases v28.0.
    """
    cfg_image_spec = ImageSpecification.from_os_image()
    with session_cloud.launch(
        user_data=UA_DAILY,
        launch_kwargs={
            "image_id": session_cloud.cloud_instance.daily_image(
                cfg_image_spec.image_id, image_type=ImageType.PRO
            )
        },
    ) as client:
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        source = get_validated_source(session_cloud)
        client.install_new_cloud_init(source)
        client.destroy()


@pytest.mark.adhoc
@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.ubuntu
class TestUbuntuAdvantagePro:
    def test_custom_services(self, session_cloud: IntegrationCloud):
        install_ua_daily(session_cloud)
        with session_cloud.launch(
            user_data=AUTO_ATTACH_CUSTOM_SERVICES,
            launch_kwargs={
                "image_id": session_cloud.snapshot_id,
            },
        ) as client:
            log = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log)
            assert did_ua_service_noop(client)
            assert is_auto_attached(client)
