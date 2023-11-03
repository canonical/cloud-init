"""Integration tests for various handlers."""

import re
from io import StringIO

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM

PER_FREQ_TEMPLATE = """\
#!/bin/bash
touch /tmp/test_per_freq_{}
"""

PER_ALWAYS_FILE = StringIO(PER_FREQ_TEMPLATE.format("always"))
PER_INSTANCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("instance"))
PER_ONCE_FILE = StringIO(PER_FREQ_TEMPLATE.format("once"))

FILES = [
    (PER_ALWAYS_FILE, "always.sh", "x-shellscript-per-boot"),
    (PER_INSTANCE_FILE, "instance.sh", "x-shellscript-per-instance"),
    (PER_ONCE_FILE, "once.sh", "x-shellscript-per-once"),
]

USER_DATA = create_mime_message(FILES)[0].as_string()


CLOUD_CONFIG_INVALID_YAML = """\
#cloud-config
ssh_import_id: [*]
"""
CLOUD_CONFIG_VALID = """\
#cloud-config
bootcmd: [echo yep]
"""

JINJA_INVALID = """\
## template:jinja
#cloud-config
runcmd:
{% for elem in (1, 2, 3) %}
- echo {{ elem }}
{% endor %}  # should be endfor
"""
JINJA_BAD_SCHEMA = """\
## template:jinja
#cloud-config
hostname: {{ range(1, 51) | random }}  # schema does not want int
"""
JINJA_VALID = """\
## template:jinja
#cloud-config
final_message:
    cloud-init the answer is: {{ 6 * 7 }}
"""

CLOUD_CONFIG_FILES = [
    (StringIO(CLOUD_CONFIG_INVALID_YAML), "cfg-invalid.yaml", "cloud-config"),
    (StringIO(CLOUD_CONFIG_VALID), "cfg-valid.yaml", "cloud-config"),
    (StringIO(JINJA_INVALID), "jinja-invalid.yaml", "jinja2"),
    (StringIO(JINJA_BAD_SCHEMA), "jinja-valid-invalid-schema.yaml", "jinja2"),
]
MIME_WITH_ERRORS = create_mime_message(CLOUD_CONFIG_FILES)[0].as_string()

CLOUD_CONFIG_ARCHIVE = """
#cloud-config-archive
- type: 'text/cloud-boothook'
  content: |
    #!/bin/sh
    echo "BOOTHOOK: $(date -R): this is called every boot." | tee /run/boothook.txt
- type: 'text/cloud-config'
  content: |
    bootcmd:
     - [sh, -c, 'echo "BOOTCMD: $(date -R): $INSTANCE_ID" | tee /run/bootcmd.txt']
"""  # noqa: E501


@pytest.mark.skipif(
    PLATFORM == "qemu", reason="QEMU only supports #cloud-config userdata"
)
@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
def test_per_freq(client: IntegrationInstance):
    # Sanity test for scripts folder
    cmd = "test -d /var/lib/cloud/scripts"
    assert client.execute(cmd).ok
    # Test per-boot
    cmd = "test -f /var/lib/cloud/scripts/per-boot/always.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_always"
    assert client.execute(cmd).ok
    # Test per-instance
    cmd = "test -f /var/lib/cloud/scripts/per-instance/instance.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_instance"
    assert client.execute(cmd).ok
    # Test per-once
    cmd = "test -f /var/lib/cloud/scripts/per-once/once.sh"
    assert client.execute(cmd).ok
    cmd = "test -f /tmp/test_per_freq_once"
    assert client.execute(cmd).ok
    client.restart()
    # Assert Always is run per boot
    cmd = "test -f /tmp/test_per_freq_always"
    assert client.execute(cmd).ok
    # Assert no per instance/once execution across reboot
    cmd = "test -f /tmp/test_per_freq_instance"
    assert client.execute(cmd).failed
    cmd = "test -f /tmp/test_per_freq_once"
    assert client.execute(cmd).failed


RE_EXPECTED_SCHEMA_STDERR = (
    r".*Error: Cloud config schema errors: format-l7.c1: Ignored invalid"
    r" user-data: cfg-invalid.yaml, hostname: \d+ is not of type 'string'"
)

RE_EXPECTED_SCHEMA_ANNOTATE = r"""#cloud-config

# from 2 files
# cfg-valid.yaml
# jinja-valid-invalid-schema.yaml

# Cloud-config part ignored SCHEMA_ERROR: cfg-invalid.yaml		# E1
---
bootcmd:
- echo yep
hostname: \d+		# E2
...

# Errors: -------------
# E1: Ignored invalid user-data: cfg-invalid.yaml
# E2: \d+ is not of type 'string'"""


@pytest.mark.skipif(
    PLATFORM == "qemu", reason="QEMU only supports #cloud-config userdata"
)
@pytest.mark.ci
@pytest.mark.user_data(MIME_WITH_ERRORS)
def test_mime_with_error_parts(client: IntegrationInstance):
    cmd = "cloud-init schema --system"
    result = client.execute(cmd)
    assert result.failed, f"Expected failure from {cmd}. Found: {result}"
    assert re.match(RE_EXPECTED_SCHEMA_STDERR, result.stderr)
    result = client.execute(f"{cmd} --annotate")
    assert re.findall(RE_EXPECTED_SCHEMA_ANNOTATE, result.stdout)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "Failed at merging in cloud config part from cfg-invalid.yaml" in log
    )


@pytest.mark.ci
@pytest.mark.user_data(CLOUD_CONFIG_ARCHIVE)
def test_cloud_config_archive_boot_hook_logging(client: IntegrationInstance):
    """
    boot-hook and bootcmd scripts run per boot and log to cloud-init-outout.log
    """
    cmd = "cloud-init schema --system"
    assert "Valid schema user-data" in client.execute(cmd).stdout
    client.restart()
    log = client.read_from_file("/var/log/cloud-init-output.log")
    assert 2 == len(re.findall("BOOTHOOK:.*", log))
    assert 2 == len(re.findall("BOOTCMD:.*", log))
