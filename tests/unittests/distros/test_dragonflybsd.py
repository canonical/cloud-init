#!/usr/bin/env python3


import cloudinit.util
from tests.unittests.helpers import mock


def test_find_dragonflybsd_part():
    assert cloudinit.util.find_dragonflybsd_part("/dev/vbd0s3") == "vbd0s3"


@mock.patch("cloudinit.util.is_DragonFlyBSD")
@mock.patch("cloudinit.subp.subp")
def test_parse_mount(mock_subp, m_is_DragonFlyBSD):
    mount_out = """
vbd0s3 on / (hammer2, local)
devfs on /dev (devfs, nosymfollow, local)
/dev/vbd0s0a on /boot (ufs, local)
procfs on /proc (procfs, local)
tmpfs on /var/run/shm (tmpfs, local)
"""

    mock_subp.return_value = (mount_out, "")
    m_is_DragonFlyBSD.return_value = True
    assert cloudinit.util.parse_mount("/") == ("vbd0s3", "hammer2", "/")
