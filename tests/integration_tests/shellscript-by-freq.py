
"""Integration tests for various handlers."""

from io import StringIO
from types import SimpleNamespace

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from tests.integration_tests.instances import IntegrationInstance

PER_FREQ_TEMPLATE = """\
#!/bin/bash
touch /var/tmp/test_per_freq_{}
"""

PER_BOOT_FILE = StringIO(PER_FREQ_TEMPLATE.format('boot'))
PER_INSTANCE_FILE = StringIO(PER_FREQ_TEMPLATE.format('instance'))
PER_ONCE_FILE = StringIO(PER_FREQ_TEMPLATE.format('once'))

args = SimpleNamespace(
    debug=False,
    list_types=False,
    files=[
        (PER_BOOT_FILE, 'boot.sh', 'x-shellscript-per-boot'),
        (PER_INSTANCE_FILE, 'instance.sh', 'x-shellscript-per-instance'),
        (PER_ONCE_FILE, 'once.sh', 'x-shellscript-per-once'),
    ]
)

USER_DATA, errors = create_mime_message(args)

@pytest.mark.user_data(USER_DATA)
def test_per_freq(client: IntegrationInstance):
    scripts = client.execute('find /var/lib/cloud/scripts -type f')
    print(scripts)