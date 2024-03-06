"""Integration test for the set_hostname module.

This module specify two tests: One updates only the hostname and the other
one updates the hostname and fqdn of the system. For both of these tests
we will check is the changes requested by the user data are being respected
after the system is boot.
"""

import pytest

from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, NOBLE

USER_DATA_HOSTNAME = """\
#cloud-config
hostname: cloudinit2
"""

USER_DATA_FQDN = """\
#cloud-config
manage_etc_hosts: true
hostname: cloudinit1
fqdn: cloudinit2.i9n.cloud-init.io
"""

USER_DATA_PREFER_FQDN = """\
#cloud-config
prefer_fqdn_over_hostname: {}
hostname: cloudinit1
fqdn: cloudinit2.test.io
"""

REQUIRES_FILE_FLAG = PLATFORM == "gce" and CURRENT_RELEASE >= NOBLE


@pytest.mark.ci
class TestHostname:
    @pytest.mark.user_data(USER_DATA_HOSTNAME)
    def test_hostname(self, client):
        hostname_output = client.execute("hostname")
        if REQUIRES_FILE_FLAG:
            assert "cloudinit2" not in hostname_output.strip()
        else:
            assert "cloudinit2" in hostname_output.strip(), CURRENT_RELEASE

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN.format(True))
    def test_prefer_fqdn(self, client):
        hostname_output = client.execute("hostname")
        if REQUIRES_FILE_FLAG:
            assert "cloudinit2.test.io" not in hostname_output.strip()
        else:
            assert "cloudinit2.test.io" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN.format(False))
    def test_prefer_short_hostname(self, client):
        hostname_output = client.execute("hostname")
        if REQUIRES_FILE_FLAG:
            assert "cloudinit1" not in hostname_output.strip()
        else:
            assert "cloudinit1" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_FQDN)
    def test_hostname_and_fqdn(self, client):
        hostname_output = client.execute("hostname")
        fqdn_output = client.execute("hostname --fqdn")
        host_output = client.execute("grep ^127 /etc/hosts")

        assert "127.0.0.1 localhost" in host_output
        if REQUIRES_FILE_FLAG:
            assert "cloudinit1" not in hostname_output.strip()
            assert "cloudinit2.i9n.cloud-init.io" not in fqdn_output.strip()
            assert (
                f"127.0.1.1 {fqdn_output} {hostname_output}" not in host_output
            )
        else:
            assert "cloudinit1" in hostname_output.strip()
            assert "cloudinit2.i9n.cloud-init.io" in fqdn_output.strip()
            assert f"127.0.1.1 {fqdn_output} {hostname_output}" in host_output


USER_DATA_HOSTNAME_FILE = """\
#cloud-config
hostname: cloudinit2
create_hostname_file: true
"""

USER_DATA_FQDN_FILE = """\
#cloud-config
manage_etc_hosts: true
hostname: cloudinit1
fqdn: cloudinit2.i9n.cloud-init.io
create_hostname_file: true
"""

USER_DATA_PREFER_FQDN_FILE = """\
#cloud-config
prefer_fqdn_over_hostname: {}
hostname: cloudinit1
fqdn: cloudinit2.test.io
create_hostname_file: true
"""


class TestCreateHostnameFile:
    @pytest.mark.user_data(USER_DATA_HOSTNAME_FILE)
    def test_hostname(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit2" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN_FILE.format(True))
    def test_prefer_fqdn(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit2.test.io" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN_FILE.format(False))
    def test_prefer_short_hostname(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit1" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_FQDN_FILE)
    def test_hostname_and_fqdn(self, client):
        hostname_output = client.execute("hostname")
        fqdn_output = client.execute("hostname --fqdn")
        host_output = client.execute("grep ^127 /etc/hosts")

        assert "cloudinit1" in hostname_output.strip()
        assert "cloudinit2.i9n.cloud-init.io" in fqdn_output.strip()
        assert f"127.0.1.1 {fqdn_output} {hostname_output}" in host_output
        assert "127.0.0.1 localhost" in host_output
