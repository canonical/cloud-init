import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_log


def customize_client(client: IntegrationInstance):
    assert client.execute(
        "echo '/tmp /var/tmp none rw,noexec,nosuid,nodev,bind 0 0'"
        " | sudo tee -a /etc/fstab"
    ).ok
    client.execute("cloud-init clean --logs")
    client.restart()


@pytest.mark.adhoc
@pytest.mark.skipif(
    PLATFORM not in ["azure", "ec2", "gce", "oci", "openstack"],
    reason=f"Test hasn't been tested on {PLATFORM}",
)
def test_dhcp_tmp_noexec(client: IntegrationInstance):
    customize_client(client)
    assert (
        "noexec" in client.execute('grep "/var/tmp" /proc/mounts').stdout
    ), "Precondition error: /var/tmp is not mounted as noexec"
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "dhclient did not produce expected files: dhcp.leases, dhclient.pid"
        not in log
    )
    verify_clean_log(log)
