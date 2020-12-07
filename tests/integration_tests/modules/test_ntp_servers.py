"""Integration test for the ntp module's ``servers`` functionality with ntp.

This test specifies the use of the `ntp` NTP client, and ensures that the given
NTP servers are configured as expected.

(This is ported from ``tests/cloud_tests/testcases/modules/ntp_servers.yaml``.)
"""
import re

import yaml
import pytest

USER_DATA = """\
#cloud-config
ntp:
  ntp_client: ntp
  servers:
      - 172.16.15.14
      - 172.16.17.18
"""

EXPECTED_SERVERS = yaml.safe_load(USER_DATA)["ntp"]["servers"]


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestNtpServers:

    def test_ntp_installed(self, class_client):
        """Test that `ntpd --version` succeeds, indicating installation."""
        result = class_client.execute("ntpd --version")
        assert 0 == result.return_code

    def test_dist_config_file_is_empty(self, class_client):
        """Test that the distributed config file is empty.

        (This test is skipped on all currently supported Ubuntu releases, so
        may not actually be needed any longer.)
        """
        if class_client.execute("test -e /etc/ntp.conf.dist").failed:
            pytest.skip("/etc/ntp.conf.dist does not exist")
        dist_file = class_client.read_from_file("/etc/ntp.conf.dist")
        assert 0 == len(dist_file.strip().splitlines())

    def test_ntp_entries(self, class_client):
        ntp_conf = class_client.read_from_file("/etc/ntp.conf")
        for expected_server in EXPECTED_SERVERS:
            assert re.search(
                r"^server {} iburst".format(expected_server),
                ntp_conf,
                re.MULTILINE
            )

    def test_ntpq_servers(self, class_client):
        result = class_client.execute("ntpq -p -w -n")
        assert result.ok
        for expected_server in EXPECTED_SERVERS:
            assert expected_server in result.stdout
