import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log


def customize_client(client: IntegrationInstance):
    assert client.execute(
        "echo '/tmp /var/tmp none rw,noexec,nosuid,nodev,bind 0 0'"
        " | sudo tee -a /etc/fstab"
    ).ok
    client.execute("cloud-init clean --logs")
    client.restart()


@pytest.mark.adhoc
@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.oci
@pytest.mark.openstack
def test_dhcp_tmp_noexec(client: IntegrationInstance):
    customize_client(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "dhclient did not produce expected files: dhcp.leases, dhclient.pid"
        not in log
    )
    verify_clean_log(log)
