"""test that ds-identify works as expected"""

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_log, wait_for_cloud_init

DATASOURCE_LIST_FILE = "/etc/cloud/cloud.cfg.d/90_dpkg.cfg"
MAP_PLATFORM_TO_DATASOURCE = {
    "lxd_container": "lxd",
    "lxd_vm": "lxd",
    "qemu": "nocloud",
    "ec2": "aws",
    "oci": "oracle",
}


def test_ds_identify(client: IntegrationInstance):
    """Verify that ds-identify works correctly

    Deb packaging often a defines datasource_list with a single datasource,
    which bypasses ds-identify logic. This tests works by removing this file
    and verifying that cloud-init doesn't experience issues.
    """
    assert client.execute(f"rm {DATASOURCE_LIST_FILE}")
    assert client.execute("cloud-init clean --logs")
    client.restart()
    wait_for_cloud_init(client)
    verify_clean_log(client.execute("cat /var/log/cloud-init.log"))
    assert client.execute("cloud-init status --wait")

    datasource = MAP_PLATFORM_TO_DATASOURCE.get(PLATFORM, PLATFORM)
    cloud_id = client.execute("cloud-id")
    assert cloud_id.ok
    assert datasource == cloud_id.stdout.rstrip()
