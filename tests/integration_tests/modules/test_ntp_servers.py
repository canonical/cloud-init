"""Integration test for the ntp module's ntp functionality.

This test specifies the use of the `ntp` NTP client, and ensures that the given
NTP servers are configured as expected.

(This is ported from ``tests/cloud_tests/testcases/modules/ntp_servers.yaml``,
``tests/cloud_tests/testcases/modules/ntp_pools.yaml``,
and ``tests/cloud_tests/testcases/modules/ntp_chrony.yaml``)
"""
import re

import pytest
import yaml

from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
ntp:
  ntp_client: ntp
  servers:
      - 172.16.15.14
      - 172.16.17.18
  pools:
      - 0.cloud-init.mypool
      - 1.cloud-init.mypool
      - 172.16.15.15
"""

EXPECTED_SERVERS = yaml.safe_load(USER_DATA)["ntp"]["servers"]
EXPECTED_POOLS = yaml.safe_load(USER_DATA)["ntp"]["pools"]


@pytest.mark.user_data(USER_DATA)
class TestNtpServers:
    def test_ntp_installed(self, class_client: IntegrationInstance):
        """Test that `ntpd --version` succeeds, indicating installation."""
        assert class_client.execute("ntpd --version").ok

    def test_dist_config_file_is_empty(
        self, class_client: IntegrationInstance
    ):
        """Test that the distributed config file is empty.

        (This test is skipped on all currently supported Ubuntu releases, so
        may not actually be needed any longer.)
        """
        if class_client.execute("test -e /etc/ntp.conf.dist").failed:
            pytest.skip("/etc/ntp.conf.dist does not exist")
        dist_file = class_client.read_from_file("/etc/ntp.conf.dist")
        assert 0 == len(dist_file.strip().splitlines())

    def test_ntp_entries(self, class_client: IntegrationInstance):
        ntp_conf = class_client.read_from_file("/etc/ntp.conf")
        for expected_server in EXPECTED_SERVERS:
            assert re.search(
                r"^server {} iburst".format(expected_server),
                ntp_conf,
                re.MULTILINE,
            )
        for expected_pool in EXPECTED_POOLS:
            assert re.search(
                r"^pool {} iburst".format(expected_pool),
                ntp_conf,
                re.MULTILINE,
            )

    def test_ntpq_servers(self, class_client: IntegrationInstance):
        result = class_client.execute("ntpq -p -w -n")
        assert result.ok
        for expected_server_or_pool in [*EXPECTED_SERVERS, *EXPECTED_POOLS]:
            assert expected_server_or_pool in result.stdout


CHRONY_DATA = """\
#cloud-config
ntp:
  enabled: true
  ntp_client: chrony
  servers:
      - 172.16.15.14
"""


@pytest.mark.user_data(CHRONY_DATA)
def test_chrony(client: IntegrationInstance):
    if client.execute("test -f /etc/chrony.conf").ok:
        chrony_conf = "/etc/chrony.conf"
    else:
        chrony_conf = "/etc/chrony/chrony.conf"
    contents = client.read_from_file(chrony_conf)
    assert "server 172.16.15.14" in contents


TIMESYNCD_DATA = """\
#cloud-config
ntp:
  enabled: true
  ntp_client: systemd-timesyncd
  servers:
      - 172.16.15.14
"""


@pytest.mark.user_data(TIMESYNCD_DATA)
def test_timesyncd(client: IntegrationInstance):
    contents = client.read_from_file(
        "/etc/systemd/timesyncd.conf.d/cloud-init.conf"
    )
    assert "NTP=172.16.15.14" in contents


EMPTY_NTP = """\
#cloud-config
ntp:
  ntp_client: ntp
  pools: []
  servers: []
"""


@pytest.mark.user_data(EMPTY_NTP)
def test_empty_ntp(client: IntegrationInstance):
    assert client.execute("ntpd --version").ok
    assert client.execute("test -f /etc/ntp.conf.dist").failed
    assert "pool.ntp.org iburst" in client.execute(
        'grep -v "^#" /etc/ntp.conf'
    )
