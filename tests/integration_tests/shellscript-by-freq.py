"""Integration tests for various handlers."""

from io import StringIO

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from tests.integration_tests.instances import IntegrationInstance

PER_FREQ_TEMPLATE = """\
#!/bin/bash
touch /tmp/test_per_freq_{}
"""

PER_BOOT_FILE = StringIO(PER_FREQ_TEMPLATE.format("boot"))
PER_INSTANCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("instance"))
PER_ONCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("once"))

FILES = [
    (PER_BOOT_FILE, "boot.sh", "x-shellscript-per-boot"),
    (PER_INSTANCE_FILE, "instance.sh", "x-shellscript-per-instance"),
    (PER_ONCE_FILE, "once.sh", "x-shellscript-per-once"),
]

USER_DATA, errors = create_mime_message(FILES)


@pytest.mark.user_data(USER_DATA)
def test_per_freq(client: IntegrationInstance):
    # Sanity test for scripts folder
    cmd = "test -d /var/lib/cloud/scripts"
    assert client.execute(cmd).ok
    # Test per-boot
    cmd = "test -f /var/lib/cloud/scripts/per-boot/boot.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_boot"
    assert client.execute(cmd).ok
    # Test per-instance
    cmd = "test -f /var/lib/cloud/scripts/per-boot/instance.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_instance"
    assert client.execute(cmd).ok
    # Test per-once
    cmd = "test -f /var/lib/cloud/scripts/per-boot/once.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_once"
    assert client.execute(cmd).ok
