import json
import os
import pathlib
from uuid import uuid4

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import IS_UBUNTU

DISK_PATH = "/tmp/test_disk_setup_{}".format(uuid4())


def setup_and_mount_lxd_disk(instance: LXDInstance):
    subp(
        "lxc config device add {} test-disk-setup-disk disk source={}".format(
            instance.name, DISK_PATH
        ).split()
    )


@pytest.fixture(scope="class", autouse=True)
def create_disk():
    """Create 16M sparse file"""
    pathlib.Path(DISK_PATH).touch()
    os.truncate(DISK_PATH, 1 << 24)
    yield
    os.remove(DISK_PATH)


# Create undersized partition in bootcmd
ALIAS_USERDATA = """\
#cloud-config
bootcmd:
  - parted /dev/sdb --script                \
          mklabel gpt                       \
          mkpart primary 0 1MiB
  - parted /dev/sdb --script print
growpart:
  devices:
  - "/"
  - "/dev/sdb1"
runcmd:
  - parted /dev/sdb --script print
"""


@pytest.mark.user_data(ALIAS_USERDATA)
@pytest.mark.lxd_setup.with_args(setup_and_mount_lxd_disk)
@pytest.mark.skipif(not IS_UBUNTU, reason="Only ever tested on Ubuntu")
@pytest.mark.skipif(
    PLATFORM != "lxd_vm", reason="Test requires additional mounted device"
)
class TestGrowPart:
    """Test growpart"""

    def test_grow_part(self, client: IntegrationInstance):
        """Verify"""
        log = client.read_from_file("/var/log/cloud-init.log")
        assert (
            "cc_growpart.py[INFO]: '/dev/sdb1' resized:"
            " changed (/dev/sdb1)" in log
        )

        lsblk = json.loads(client.execute("lsblk --json"))
        sdb = [x for x in lsblk["blockdevices"] if x["name"] == "sdb"][0]
        assert len(sdb["children"]) == 1
        assert sdb["children"][0]["name"] == "sdb1"
        assert sdb["size"] == "16M"


@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires loop device and LVM which need VM isolation",
)
class TestGrowPartLVM:
    """
    Test that LVM partitions are correctly resized.

    This test uses a bootcmd to create a loop device and partition it using
    LVM.  The underlying partition does not used the whole loop "disk", nor
    does the Logical Volume we create use the whole of the Physical Volume.

    This test checks that, after boot, the Logical Volume has been resized to
    use the whole loop device (with some allowance for partitioning/LVM
    overhead).
    """

    # These steps pulled from https://ops.tips/blog/lvm-on-loopback-devices/
    LVM_USER_DATA = """\
    #cloud-config
    bootcmd:
        # Create our LVM "disk"
        - dd if=/dev/zero of=/lvm0.img bs=50 count=1M
        # Use loop7 because snaps take up the early numbers
        - losetup /dev/loop7 /lvm0.img
        # Create an LVM partition on the first half of the disk
        - echo "start=1,size=25M,type=8e" | sfdisk /dev/loop7
        # Update the kernel's partition table
        - partx --update /dev/loop7
        # Create our LVM PV and VG
        - pvcreate /dev/loop7p1
        - vgcreate myvg /dev/loop7p1
        # Create our LV with a smaller size than the whole PV
        - lvcreate --size 10M --name lv1 myvg
        # Create a filesystem to resize
        - mkfs.ext4 /dev/mapper/myvg-lv1
    growpart:
        devices: ["/dev/mapper/myvg-lv1"]
    """

    # Our disk is 50M; with 4MB extents, this will mean 48M for the Logical
    # Volume, so use a slightly lower threshold than that
    LVM_LOWER_THRESHOLD = 47 * 1024 * 1024

    @pytest.mark.user_data(LVM_USER_DATA)
    def test_resize_successful(self, client):
        def _get_size_of(device):
            ret = client.execute(
                ["lsblk", "-b", "--output", "SIZE", "-n", "-d", device]
            )
            if ret.ok:
                return int(ret.stdout.strip())
            pytest.fail("Failed to get size of {}: {}".format(device, ret))

        assert _get_size_of("/dev/loop7p1") > self.LVM_LOWER_THRESHOLD
        assert _get_size_of("/dev/mapper/myvg-lv1") > self.LVM_LOWER_THRESHOLD
