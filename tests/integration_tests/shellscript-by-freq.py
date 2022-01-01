
"""Integration tests for various handlers."""

from io import StringIO
from types import SimpleNamespace

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from tests.integration_tests.instances import IntegrationInstance

PER_FREQ_TEMPLATE = """\
#!/bin/bash
touch /tmp/test_per_freq_{}
"""

PER_BOOT_FILE = StringIO(PER_FREQ_TEMPLATE.format('boot'))
PER_INSTANCE_FILE = StringIO(PER_FREQ_TEMPLATE.format('instance'))
PER_ONCE_FILE = StringIO(PER_FREQ_TEMPLATE.format('once'))

# args = SimpleNamespace(
#     debug=False,
#     list_types=False,
#     files=[
#         (PER_BOOT_FILE, 'boot.sh', 'x-shellscript-per-boot'),
#         (PER_INSTANCE_FILE, 'instance.sh', 'x-shellscript-per-instance'),
#         (PER_ONCE_FILE, 'once.sh', 'x-shellscript-per-once'),
#     ]
# )

FILES=[
    (PER_BOOT_FILE, 'boot.sh', 'x-shellscript-per-boot'),
    (PER_INSTANCE_FILE, 'instance.sh', 'x-shellscript-per-instance'),
    (PER_ONCE_FILE, 'once.sh', 'x-shellscript-per-once'),
]

USER_DATA, errors = create_mime_message(FILES)
print(f'errors={errors}')
print(f'USER_DATA=${USER_DATA}')
@pytest.mark.user_data(USER_DATA)
def test_per_freq(client: IntegrationInstance):
    print('checking /v/l/c/scripts exists ...')
    rc_ok = client.execute('test -d /var/lib/cloud/scripts').ok
    assert rc_ok is True
    print('checking /v/l/c/s/per-boot/boot.sh exists ...')
    rc_ok = client.execute('test -f /var/lib/cloud/scripts/per-boot/boot.sh').ok
    assert rc_ok is True
    print('checking /v/tmp/c/test_per_freq_boot exists ...')
    rc_ok = client.execute('test -f /var/tmp/test_per_freq_boot').ok
    assert rc_ok is True
    pass
