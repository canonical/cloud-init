"""Integration test for the snap module.

This test specifies a command to be executed by the ``snap`` module
and then checks that if that command was executed during boot.

(This is ported from
``tests/cloud_tests/testcases/modules/runcmd.yaml``.)"""

import pytest


USER_DATA = """\
#cloud-config
package_update: true
snap:
  squashfuse_in_container: true
  commands:
    - snap install hello-world
"""


@pytest.mark.ci
class TestSnap:

    @pytest.mark.user_data(USER_DATA)
    def test_snap(self, client):
        snap_output = client.execute("snap list")
        assert "core " in snap_output
        assert "hello-world " in snap_output
