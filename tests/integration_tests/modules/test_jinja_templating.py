# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import (
    verify_clean_log,
    verify_ordered_items_in_text,
)

MERGED_CFG_DOC = (
    "Merged cloud-init system config from /etc/cloud/cloud.cfg "
    "and /etc/cloud/cloud.cfg.d/"
)

USER_DATA = """\
## template: jinja
#cloud-config
runcmd:
  - echo {{v1.local_hostname}} > /var/tmp/runcmd_output
  - echo {{merged_system_cfg._doc}} >> /var/tmp/runcmd_output
  - echo {{v1['local-hostname']}} >> /var/tmp/runcmd_output
"""


@pytest.mark.skipif(
    PLATFORM == "qemu", reason="QEMU only supports #cloud-config header"
)
@pytest.mark.user_data(USER_DATA)
def test_runcmd_with_variable_substitution(client: IntegrationInstance):
    """Test jinja substitution.

    Ensure underscore-delimited aliases exist for hyphenated key and
    we can also substitute variables from instance-data-sensitive
    LP: #1931392.
    """
    hostname = client.execute("hostname").stdout.strip()
    expected = [hostname, MERGED_CFG_DOC, hostname]
    output = client.read_from_file("/var/tmp/runcmd_output")
    verify_ordered_items_in_text(expected, output)


@pytest.mark.ci
def test_substitution_in_etc_cloud(client: IntegrationInstance):
    orig_etc_cloud = client.read_from_file("/etc/cloud/cloud.cfg")
    assert "## template: jinja" not in orig_etc_cloud

    new_etc_cloud = (
        "## template: jinja\n\n"
        f"{orig_etc_cloud}\n\n"
        "runcmd:\n"
        " - echo {{v1.local_hostname}} > /var/tmp/runcmd_output\n"
    )
    client.write_to_file("/etc/cloud/cloud.cfg", new_etc_cloud)

    new_cloud_part = (
        "## template: jinja\n"
        "bootcmd:\n"
        " - echo '{{merged_system_cfg._doc}}' > /var/tmp/bootcmd_output\n"
    )
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/50-jinja-test.cfg", new_cloud_part
    )

    cloud_part_no_jinja = "final_message: final hi {{v1.local_hostname}}"
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/70-no-jinja-test.cfg", cloud_part_no_jinja
    )

    client.execute("cloud-init clean --logs")
    client.restart()

    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)

    # Ensure /etc/cloud/cloud.cfg template works as expected
    hostname = client.execute("hostname").stdout.strip()
    assert client.read_from_file("/var/tmp/runcmd_output").strip() == hostname

    # Ensure /etc/cloud/cloud.cfg.d template works as expected
    assert (
        client.read_from_file("/var/tmp/bootcmd_output").strip()
        == MERGED_CFG_DOC
    )

    # Ensure a file without '## template: jinja' isn't interpreted as jinja
    assert "final hi {{v1.local_hostname}}" in log


def test_invalid_etc_cloud_substitution(client: IntegrationInstance):
    no_var_part = (
        "## template: jinja\n"
        "runcmd:\n"
        " - echo {{bad}} > /var/tmp/runcmd_bad\n"
        " - echo {{v1.local_hostname}} > /var/tmp/runcmd_output\n"
        "final_message: final hi {{v1.local_hostname}}"
    )
    client.write_to_file("/etc/cloud/cloud.cfg.d/50-no-var.cfg", no_var_part)

    normal_part = "bootcmd:\n - echo hi > /var/tmp/bootcmd_output\n"
    client.write_to_file("/etc/cloud/cloud.cfg.d/60-normal.cfg", normal_part)

    client.execute("cloud-init clean --logs")
    client.restart()

    log = client.read_from_file("/var/log/cloud-init.log")

    # Ensure we get warning from invalid jinja var
    assert (
        "jinja_template.py[WARNING]: Could not render jinja template "
        "variables in file '/etc/cloud/cloud.cfg.d/50-no-var.cfg': "
        "'bad'"
    ) in log

    # Ensure the file was still processed with invalid var
    assert (
        client.read_from_file("/var/tmp/runcmd_bad").strip()
        == "CI_MISSING_JINJA_VAR/bad"
    )
    hostname = client.execute("hostname").stdout.strip()
    assert client.read_from_file("/var/tmp/runcmd_output").strip() == hostname
    assert f"final hi {hostname}" in log

    # Ensure other files continue to load correctly
    assert client.read_from_file("/var/tmp/bootcmd_output").strip() == "hi"
