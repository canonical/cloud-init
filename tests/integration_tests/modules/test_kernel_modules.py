"""Integration test for kernel_modules module."""
import pytest

from tests.integration_tests.instances import IntegrationInstance

ASCII_TEXT = "ASCII text"

USER_DATA = """\
#cloud-config
packages:
  - zfsutils-linux
  - wireguard
  - multipath-tools
kernel_modules:
  - name: lockd
    load: true
    persist:
      options: "nlm_udpport=4045 nlm_tcpport=4045"
  - name: wireguard
  - name: zfs
    load: true
  - name: dm_multipath
    persist:
      blacklist: true
"""


@pytest.mark.user_data(USER_DATA)
@pytest.mark.ci
@pytest.mark.ubuntu
class TestKernelModules:
    @pytest.mark.parametrize(
        "cmd,expected_out",
        (
            # check permissions
            (
                "stat -c '%U %a' /etc/modules-load.d/cloud-init.conf",
                r"root 600",
            ),
            ("stat -c '%U %a' /etc/modprobe.d/cloud-init.conf", r"root 600"),
            # ASCII check
            ("file /etc/modules-load.d/cloud-init.conf", ASCII_TEXT),
            ("file /etc/modprobe.d/cloud-init.conf", ASCII_TEXT),
            # check loaded modules
            ("lsmod | grep -e '^lockd\\|^zfs' | wc -l", "2"),
        ),
    )
    def test_kernel_modules(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        result = class_client.execute(cmd)
        assert result.ok
        assert expected_out in result.stdout
