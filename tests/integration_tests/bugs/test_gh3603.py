"""Integration test for gh-3603.

cc_mounts historically wrote /etc/fstab entries without escaping, so a
space in the device (fs_spec) or mount point (fs_file) produced an
unparseable line and broke ``mount -a``. Verify that a mount point
containing a space is octal-escaped in /etc/fstab, that cloud-init logs
stay clean, and that the real (unescaped) directory is created.

A network fs_spec (contains ``:``) with ``noauto`` keeps the entry in
fstab without cloud-init attempting the actual mount, so the test does
not depend on any real device or NFS server.

https://github.com/canonical/cloud-init/issues/3603
"""

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
mounts:
- - server.example:/export
  - /mnt/Cdrom Drive
  - nfs
  - defaults,noauto
  - "0"
  - "0"
"""


@pytest.mark.user_data(USER_DATA)
def test_mount_point_with_space_is_escaped(client: IntegrationInstance):
    # cloud-init should have configured mounts without any errors.
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert "SUCCESS: config-mounts ran successfully" in log

    # The space must be octal-escaped (\040) in the /etc/fstab entry.
    fstab = client.read_from_file("/etc/fstab")
    assert "/mnt/Cdrom\\040Drive" in fstab

    # The real directory (with a literal space) must have been created.
    assert client.execute("test -d '/mnt/Cdrom Drive'").ok
