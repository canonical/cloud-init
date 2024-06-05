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
            " changed (/dev/sdb1) from" in log
        )

        lsblk = json.loads(client.execute("lsblk --json"))
        sdb = [x for x in lsblk["blockdevices"] if x["name"] == "sdb"][0]
        assert len(sdb["children"]) == 1
        assert sdb["children"][0]["name"] == "sdb1"
        assert sdb["size"] == "16M"
