import json
import os
from uuid import uuid4

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

DISK_PATH = "/tmp/test_disk_setup_{}".format(uuid4())


def setup_and_mount_lxd_disk(instance: LXDInstance):
    subp(
        "lxc config device add {} test-disk-setup-disk disk source={}".format(
            instance.name, DISK_PATH
        ).split()
    )


@pytest.fixture
def create_disk():
    # 640k should be enough for anybody
    subp("dd if=/dev/zero of={} bs=1k count=640".format(DISK_PATH).split())
    yield
    os.remove(DISK_PATH)


ALIAS_USERDATA = """\
#cloud-config
device_aliases:
  my_alias: /dev/sdb
disk_setup:
  my_alias:
    table_type: mbr
    layout: [50, 50]
    overwrite: True
fs_setup:
- label: fs1
  device: my_alias.1
  filesystem: ext4
- label: fs2
  device: my_alias.2
  filesystem: ext4
mounts:
- ["my_alias.1", "/mnt1"]
- ["my_alias.2", "/mnt2"]
"""


@pytest.mark.user_data(ALIAS_USERDATA)
@pytest.mark.lxd_setup.with_args(setup_and_mount_lxd_disk)
@pytest.mark.ubuntu
@pytest.mark.lxd_vm
class TestDeviceAliases:
    """Test devices aliases work on disk setup/mount"""

    def test_device_alias(self, create_disk, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        assert (
            "updated disk_setup device entry 'my_alias' to '/dev/sdb'" in log
        )
        assert "changed my_alias.1 => /dev/sdb1" in log
        assert "changed my_alias.2 => /dev/sdb2" in log
        verify_clean_log(log)

        lsblk = json.loads(client.execute("lsblk --json"))
        sdb = [x for x in lsblk["blockdevices"] if x["name"] == "sdb"][0]
        assert len(sdb["children"]) == 2
        assert sdb["children"][0]["name"] == "sdb1"
        assert sdb["children"][1]["name"] == "sdb2"
        if "mountpoint" in sdb["children"][0]:
            assert sdb["children"][0]["mountpoint"] == "/mnt1"
            assert sdb["children"][1]["mountpoint"] == "/mnt2"
        else:
            assert sdb["children"][0]["mountpoints"] == ["/mnt1"]
            assert sdb["children"][1]["mountpoints"] == ["/mnt2"]
        result = client.execute("mount -a")
        assert result.return_code == 0
        assert result.stdout.strip() == ""
        assert result.stderr.strip() == ""
        result = client.execute("findmnt -J /mnt1")
        assert result.return_code == 0
        result = client.execute("findmnt -J /mnt2")
        assert result.return_code == 0


PARTPROBE_USERDATA = """\
#cloud-config
disk_setup:
  /dev/sdb:
    table_type: mbr
    layout: [50, 50]
    overwrite: True
fs_setup:
  - label: test
    device: /dev/sdb1
    filesystem: ext4
  - label: test2
    device: /dev/sdb2
    filesystem: ext4
mounts:
- ["/dev/sdb1", "/mnt1"]
- ["/dev/sdb2", "/mnt2"]
"""

UPDATED_PARTPROBE_USERDATA = """\
#cloud-config
disk_setup:
  /dev/sdb:
    table_type: mbr
    layout: [100]
    overwrite: True
fs_setup:
  - label: test3
    device: /dev/sdb1
    filesystem: ext4
mounts:
- ["/dev/sdb1", "/mnt3"]
"""


@pytest.mark.user_data(PARTPROBE_USERDATA)
@pytest.mark.lxd_setup.with_args(setup_and_mount_lxd_disk)
@pytest.mark.ubuntu
@pytest.mark.lxd_vm
class TestPartProbeAvailability:
    """Test disk setup works with partprobe

    Disk setup can run successfully on a mounted partition when
    partprobe is being used.

    lp-1920939
    """

    def _verify_first_disk_setup(self, client, log):
        verify_clean_log(log)
        lsblk = json.loads(client.execute("lsblk --json"))
        sdb = [x for x in lsblk["blockdevices"] if x["name"] == "sdb"][0]
        assert len(sdb["children"]) == 2
        assert sdb["children"][0]["name"] == "sdb1"
        assert sdb["children"][1]["name"] == "sdb2"
        if "mountpoint" in sdb["children"][0]:
            assert sdb["children"][0]["mountpoint"] == "/mnt1"
            assert sdb["children"][1]["mountpoint"] == "/mnt2"
        else:
            assert sdb["children"][0]["mountpoints"] == ["/mnt1"]
            assert sdb["children"][1]["mountpoints"] == ["/mnt2"]

    # Not bionic because the LXD agent gets in the way of us
    # changing the userdata
    @pytest.mark.not_bionic
    def test_disk_setup_when_mounted(
        self, create_disk, client: IntegrationInstance
    ):
        """Test lp-1920939.

        We insert an extra disk into our VM, format it to have two partitions,
        modify our cloud config to mount devices before disk setup, and modify
        our userdata to setup a single partition on the disk.

        This allows cloud-init to attempt disk setup on a mounted partition.
        When blockdev is in use, it will fail with
        "blockdev: ioctl error on BLKRRPART: Device or resource busy" along
        with a warning and a traceback. When partprobe is in use, everything
        should work successfully.
        """
        log = client.read_from_file("/var/log/cloud-init.log")
        self._verify_first_disk_setup(client, log)

        # Update our userdata and cloud.cfg to mount then perform new disk
        # setup
        client.write_to_file(
            "/var/lib/cloud/seed/nocloud-net/user-data",
            UPDATED_PARTPROBE_USERDATA,
        )
        client.execute(
            "sed -i 's/write-files/write-files\\n - mounts/' "
            "/etc/cloud/cloud.cfg"
        )

        client.execute("cloud-init clean --logs")
        client.restart()

        # Assert new setup works as expected
        verify_clean_log(log)

        lsblk = json.loads(client.execute("lsblk --json"))
        sdb = [x for x in lsblk["blockdevices"] if x["name"] == "sdb"][0]
        assert len(sdb["children"]) == 1
        assert sdb["children"][0]["name"] == "sdb1"
        if "mountpoint" in sdb["children"][0]:
            assert sdb["children"][0]["mountpoint"] == "/mnt3"
        else:
            assert sdb["children"][0]["mountpoints"] == ["/mnt3"]

    def test_disk_setup_no_partprobe(
        self, create_disk, client: IntegrationInstance
    ):
        """Ensure disk setup still works as expected without partprobe."""
        # We can't do this part in a bootcmd because the path has already
        # been found by the time we get to the bootcmd
        client.execute("rm $(which partprobe)")
        client.execute("cloud-init clean --logs")
        client.restart()

        log = client.read_from_file("/var/log/cloud-init.log")
        self._verify_first_disk_setup(client, log)

        assert "partprobe" not in log
