"""QemuFwCfg datasource integration tests."""

import os
import pathlib

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_boot

FWCFG_PREFIX = "opt/io.cloud-init/cloud-init"

META_DATA = '{"instance-id":"test-vm","local-hostname":"test-vm"}'
USER_DATA = "#cloud-config\nruncmd:\n  - touch /var/tmp/qemufwcfg_test_file"


def _write_datafile(content: str, name: str) -> str:
    path = os.path.join(pathlib.Path.home(), f"qemufwcfg_{name}")
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.fixture(scope="class", autouse=True)
def cleanup_datafiles():
    """Delete host-side fw_cfg files after the class's tests finish."""
    yield
    for name in ("meta-data", "user-data"):
        try:
            os.unlink(os.path.join(pathlib.Path.home(), f"qemufwcfg_{name}"))
        except OSError:
            pass


def setup_qemufwcfg(instance: LXDInstance):
    meta_data_path = _write_datafile(META_DATA, "meta-data")
    user_data_path = _write_datafile(USER_DATA, "user-data")
    home = pathlib.Path.home()
    subp(
        [
            "lxc",
            "config",
            "set",
            instance.name,
            f"raw.apparmor=file {home}/** r,",
        ]
    )
    subp(
        [
            "lxc",
            "config",
            "set",
            instance.name,
            "raw.qemu="
            f"-fw_cfg name={FWCFG_PREFIX}/meta-data,file={meta_data_path} "
            f"-fw_cfg name={FWCFG_PREFIX}/user-data,file={user_data_path}",
        ]
    )


@pytest.mark.lxd_setup.with_args(setup_qemufwcfg)
@pytest.mark.lxd_use_exec
@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="fw_cfg requires a QEMU-based VM",
)
class TestQemuFwCfg:
    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def configure_and_reboot(cls, class_client: IntegrationInstance):
        """Override datasource_list and reboot so QemuFwCfg is selected.

        90_dpkg.cfg from the Ubuntu package overrides datasource_list without
        QemuFwCfg. Write a higher-priority config on the running instance,
        clean cloud-init state, and restart so the second boot uses QemuFwCfg.
        """
        class_client.write_to_file(
            "/etc/cloud/cloud.cfg.d/99-qemufwcfg.cfg",
            "datasource_list: [QemuFwCfg, None]\n",
        )
        # qemu_fw_cfg is compiled as a module (CONFIG_FW_CFG_SYSFS=m) but
        # ships in linux-modules-extra, not installed by default.  Install it
        # and add it to /etc/modules so systemd-modules-load loads it on boot
        # before cloud-init-local.service starts.
        class_client.execute(
            "apt-get install -qy linux-modules-extra-$(uname -r)"
        )
        class_client.execute("echo qemu_fw_cfg >> /etc/modules")
        class_client.execute("cloud-init clean --logs")
        class_client.restart()

    def test_datasource_detected(self, class_client: IntegrationInstance):
        """QemuFwCfg datasource is selected when fw_cfg slots are present."""
        log = class_client.execute("cat /var/log/cloud-init.log").stdout
        assert "DataSourceQemuFwCfg" in log

    def test_userdata_applied(self, class_client: IntegrationInstance):
        """user-data delivered via fw_cfg is executed by cloud-init."""
        assert class_client.execute("test -f /var/tmp/qemufwcfg_test_file").ok

    def test_metadata_applied(self, class_client: IntegrationInstance):
        """meta-data delivered via fw_cfg sets hostname."""
        assert "test-vm" == class_client.execute("hostname").stdout.strip()

    def test_clean_boot(self, class_client: IntegrationInstance):
        """Boot completes without errors or unexpected warnings."""
        verify_clean_boot(class_client)

    def test_fwcfg_slots_visible_in_sysfs(
        self, class_client: IntegrationInstance
    ):
        """fw_cfg entries are accessible via the kernel sysfs driver."""
        assert class_client.execute(
            f"test -f /sys/firmware/qemu_fw_cfg/by_name/"
            f"{FWCFG_PREFIX}/user-data/raw"
        ).ok
