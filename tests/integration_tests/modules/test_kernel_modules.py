"""Integration test for kernel_modules module."""
import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

ASCII_TEXT = "ASCII text"

USER_DATA = """\
#cloud-config
packages:
  - wireguard
kernel_modules:
  - name: lockd
    load: true
    persist:
      options: "nlm_udpport=4045 nlm_tcpport=4045"
  - name: wireguard
  - name: ip_tables
    load: true
  - name: ahci
    load: false
    persist:
      blacklist: true
  - name: btrfs
    load: true
    persist:
      softdep:
        pre: ["nf_conntrack" "nf_tables"]
"""

KERNEL_MODULES_LXD = "lockd,zfs,wireguard"


def load_kernel_modules_lxd(instance: LXDInstance):
    subp(
        "lxc config set {} linux.kernel_modules {}".format(
            instance.name, KERNEL_MODULES_LXD
        ).split()
    )


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
@pytest.mark.ubuntu
class BaseTest:
    @pytest.mark.parametrize(
        "cmd,expected_out",
        (
            pytest.param(
                "stat -c '%U %a' /etc/modules-load.d/50-cloud-init.conf",
                r"root 600",
                id="check-permissions",
            ),
            pytest.param(
                "stat -c '%U %a' /etc/modprobe.d/50-cloud-init.conf",
                r"root 600",
                id="check-permissions-2",
            ),
            pytest.param(
                "file /etc/modules-load.d/50-cloud-init.conf",
                ASCII_TEXT,
                id="ASCII-check",
            ),
            pytest.param(
                "file /etc/modprobe.d/50-cloud-init.conf",
                ASCII_TEXT,
                id="ASCII-check-2",
            ),
            pytest.param(
                "lsmod | grep -e '^lockd\\|^ip_tables\\|^wireguard\\|^btrfs' | wc -l",
                "4",
                id="check-loaded-modules",
            ),
            pytest.param(
                "sha256sum </etc/modules-load.d/50-cloud-init.conf",
                "9d14d5d585dd3e5e9a3c414b5b7af7ed"
                "9d44e7ee3584652fbf388cad455b5053",
                id="sha256sum-check-modules",
            ),
            pytest.param(
                "sha256sum   </etc/modprobe.d/50-cloud-init.conf",
                "229ccc941ec34fc8c49bf14285ffeb65"
                "ea2796c4840f9377d6df76bda42c878e",
                id="sha256sum-check-modprobe",
            ),
        ),
    )
    def test_kernel_modules(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        result = class_client.execute(cmd)
        assert result.ok
        assert expected_out in result.stdout

    def test_clean_log(self, class_client: IntegrationInstance):
        log = class_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)


@pytest.mark.no_container
class TestKernelModules(BaseTest):
    pass


@pytest.mark.lxd_container
@pytest.mark.lxd_setup.with_args(load_kernel_modules_lxd)
class TestKernelModulesWithoutKmod(BaseTest):
    pass
