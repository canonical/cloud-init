"""Integration tests for cc_ubuntu_autoinstall happy path"""

import pytest

from tests.integration_tests.releases import IS_UBUNTU

USER_DATA = """\
#cloud-config
autoinstall:
  version: 1
  cloudinitdoesnotvalidateotherkeyschema: true
snap:
  commands:
    - snap install subiquity --classic
"""


LOG_MSG = "Valid autoinstall schema. Config will be processed by subiquity"


@pytest.mark.skipif(not IS_UBUNTU, reason="Test is Ubuntu specific")
@pytest.mark.user_data(USER_DATA)
class TestUbuntuAutoinstall:
    def test_autoinstall_schema_valid_when_snap_present(self, class_client):
        """autoinstall directives will pass when snap is present"""
        assert "subiquity" in class_client.execute(["snap", "list"]).stdout
        log = class_client.read_from_file("/var/log/cloud-init.log")
        assert LOG_MSG in log
