"""Integration test for the runcmd module.

This test specifies a command to be executed by the ``runcmd`` module
and then checks if that command was executed during boot.

(This is ported from
``tests/cloud_tests/testcases/modules/runcmd.yaml``.)"""

import pytest


USER_DATA = """\
#cloud-config
runcmd:
 - echo cloud-init run cmd test > /var/tmp/run_cmd
"""


@pytest.mark.ci
class TestRuncmd:

    @pytest.mark.user_data(USER_DATA)
    def test_runcmd(self, client):
        runcmd_output = client.read_from_file("/var/tmp/run_cmd")
        assert runcmd_output.strip() == "cloud-init run cmd test"
