"""Integration test for output redirection.

This test redirects the output of a command to a file and then checks the file.

(This is ported from
``tests/cloud_tests/testcases/main/command_output_simple.yaml``.)"""
import pytest

from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
output: { all: "| tee -a /var/log/cloud-init-test-output" }
final_message: "should be last line in cloud-init-test-output file"
"""


@pytest.mark.user_data(USER_DATA)
def test_runcmd(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init-test-output")
    assert "should be last line in cloud-init-test-output file" in log
