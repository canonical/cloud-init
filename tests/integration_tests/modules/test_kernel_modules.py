"""Integration test for kernel_modules module."""
import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
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

KERNEL_MODULES_LXD = "lockd,zfs"


def load_kernel_modules_lxd(instance: LXDInstance):
    subp(
        "lxc config set {} linux.kernel_modules {}".format(
            instance.name, KERNEL_MODULES_LXD
        ).split()
    )


@pytest.mark.user_data(USER_DATA)
@pytest.mark.ci
@pytest.mark.lxd_vm
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
            # sha256sum check modul
            (
                "sha256sum </etc/modules-load.d/cloud-init.conf",
                "ea8244ae0b5639f26f58c7e881c31f88"
                "3c2098202694719e28f4a5adb08fd5c1",
            ),
            # sha256sum check modprobe
            (
                "sha256sum   </etc/modprobe.d/cloud-init.conf",
                "30983eed6c4d3048402ad6605f296308"
                "39551a3487f5e12875a5037c93792083",
            ),
        ),
    )
    def test_kernel_modules(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        result = class_client.execute(cmd)
        assert result.ok
        assert expected_out in result.stdout


@pytest.mark.ci
@pytest.mark.lxd_container
@pytest.mark.user_data(USER_DATA)
@pytest.mark.lxd_setup.with_args(load_kernel_modules_lxd)
@pytest.mark.ubuntu
class TestKernelModulesWithoutKmod:
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
            # sha256sum check modul
            (
                "sha256sum </etc/modules-load.d/cloud-init.conf",
                "ea8244ae0b5639f26f58c7e881c31f88"
                "3c2098202694719e28f4a5adb08fd5c1",
            ),
            # sha256sum check modprobe
            (
                "sha256sum   </etc/modprobe.d/cloud-init.conf",
                "30983eed6c4d3048402ad6605f296308"
                "39551a3487f5e12875a5037c93792083",
            ),
        ),
    )
    def test_kernel_modules(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        result = class_client.execute(cmd)
        assert result.ok
        assert expected_out in result.stdout
