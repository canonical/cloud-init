"""Integration tests for various handlers."""

from io import StringIO

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from tests.integration_tests.instances import IntegrationInstance

# from types import SimpleNamespace


PER_FREQ_TEMPLATE = """\
#!/bin/bash
touch /tmp/test_per_freq_{}
"""

PER_BOOT_FILE = StringIO(PER_FREQ_TEMPLATE.format("boot"))
PER_INSTANCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("instance"))
PER_ONCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("once"))

# args = SimpleNamespace(
#     debug=False,
#     list_types=False,
#     files=[
#         (PER_BOOT_FILE, 'boot.sh', 'x-shellscript-per-boot'),
#         (PER_INSTANCE_FILE, 'instance.sh', 'x-shellscript-per-instance'),
#         (PER_ONCE_FILE, 'once.sh', 'x-shellscript-per-once'),
#     ]
# )

FILES = [
    (PER_BOOT_FILE, "boot.sh", "x-shellscript-per-boot"),
    (PER_INSTANCE_FILE, "instance.sh", "x-shellscript-per-instance"),
    (PER_ONCE_FILE, "once.sh", "x-shellscript-per-once"),
]

USER_DATA, errors = create_mime_message(FILES)
print(f"errors={errors}")
print(f"USER_DATA=${USER_DATA}")


@pytest.mark.user_data(USER_DATA)
def test_per_freq(client: IntegrationInstance):
    print("checking /v/l/c/scripts exists ...")
    rc_ok = client.execute("test -d /var/lib/cloud/scripts").ok
    assert rc_ok is True
    # Test per-boot
    print("checking /v/l/c/s/per-boot/boot.sh exists ...")
    cmd = "test -f /var/lib/cloud/scripts/per-boot/boot.sh"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    print("checking /tmp/c/test_per_freq_boot exists ...")
    cmd = "test -f /tmp/test_per_freq_boot"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    # Test per-instance
    print("checking /v/l/c/s/per-boot/instance.sh exists ...")
    cmd = "test -f /var/lib/cloud/scripts/per-boot/instance.sh"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    print("checking /tmp/c/test_per_freq_instance exists ...")
    cmd = "test -f /tmp/test_per_freq_instance"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    # Test per-once
    print("checking /v/l/c/s/per-boot/once.sh exists ...")
    cmd = "test -f /var/lib/cloud/scripts/per-boot/once.sh"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    print("checking /tmp/c/test_per_freq_once exists ...")
    cmd = "test -f /tmp/test_per_freq_once"
    rc_ok = client.execute(cmd).ok
    assert rc_ok is True
    pass
