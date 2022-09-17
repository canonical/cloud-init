"""Integration test for the create_machine_id module."""
import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
create_machine_id: true
runcmd:
  - "touch /test.txt"
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
@pytest.mark.lxd_vm
@pytest.mark.lxd_container
@pytest.mark.gce
@pytest.mark.ec2
@pytest.mark.azure
@pytest.mark.openstack
@pytest.mark.oci
@pytest.mark.ubuntu
class TestCreateMachineID:
    @pytest.mark.parametrize(
        "cmd,expected_out",
        (
            # test if file was written for machine-id
            (
                "stat -c '%N' /etc/machine-id",
                r"'/etc/machine-id'",
            ),
            # check permissions for machine-id
            ("stat -c '%U %a' /etc/machine-id", r"root 444"),
        ),
    )
    def test_create_machine_id(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        result = class_client.execute(cmd)
        assert result.ok
        assert expected_out in result.stdout

    def test_check_log(self, class_client: IntegrationInstance):
        cloud_init_log = class_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(cloud_init_log)
        assert "Removing file" in cloud_init_log
