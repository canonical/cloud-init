import datetime

import pytest
from pycloudlib.azure.util import AzureCreateParams, AzureParams
from pycloudlib.cloud import ImageType

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import BIONIC, CURRENT_RELEASE


def _check_for_eject_errors(
    instance: IntegrationInstance,
):
    assert "sr0" not in instance.execute("mount")
    log = instance.read_from_file("/var/log/cloud-init.log")
    assert "Failed ejecting the provisioning iso" not in log


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


def parse_resolvectl_dns(output: str) -> dict:
    """Parses the output of 'resolvectl dns'.

    >>> parse_resolvectl_dns(
    ...    "Global:",
    ...    "Link 2 (eth0): 168.63.129.16",
    ...    "Link 3 (eth1): 168.63.129.16",
    ... )
    {'Global': '',
     'Link 2 (eth0)': '168.63.129.16',
     'Link 3 (eth1)': '168.63.129.16'}
    """

    parsed = dict()
    for line in output.splitlines():
        if line.isspace():
            continue
        splitted = line.split(":")
        k = splitted.pop(0).strip()
        v = splitted.pop(0).strip() if splitted else ""
        parsed[k] = v
    return parsed


@pytest.mark.skipif(PLATFORM != "azure", reason="Test is Azure specific")
@pytest.mark.skipif(
    CURRENT_RELEASE < BIONIC, reason="Easier to test on Bionic+"
)
def test_azure_multi_nic_setup(
    setup_image, session_cloud: IntegrationCloud
) -> None:
    """Integration test for https://warthogs.atlassian.net/browse/CPC-3999.

    Azure should have the primary NIC only route to DNS.
    Ensure other NICs do not have route to DNS.
    """
    us = datetime.datetime.now().strftime("%f")
    rg_params = AzureParams(f"ci-test-multi-nic-setup-{us}", None)
    nic_one = AzureCreateParams(f"ci-nic1-test-{us}", rg_params.name, None)
    nic_two = AzureCreateParams(f"ci-nic2-test-{us}", rg_params.name, None)
    with session_cloud.launch(
        launch_kwargs={
            "resource_group_params": rg_params,
            "network_interfaces_params": [nic_one, nic_two],
        }
    ) as client:
        _check_for_eject_errors(client)
        if CURRENT_RELEASE == BIONIC:
            ret = client.execute("systemd-resolve --status")
            assert ret.ok, ret.stderr
            assert ret.stdout.count("Current Scopes: DNS") == 1
        else:
            ret = client.execute("resolvectl dns")
            assert ret.ok, ret.stderr
            routes = parse_resolvectl_dns(ret.stdout)
            routes_devices = list(routes.keys())
            eth1_dev = [dev for dev in routes_devices if "(eth1)" in dev][0]
            assert not routes[eth1_dev], (
                f"Expected eth1 to not have routes to dns."
                f" Found: {routes[eth1_dev]}"
            )

        # check the instance can resolve something
        res = client.execute("resolvectl query google.com")
        assert res.ok, res.stderr
