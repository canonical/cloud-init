"""Integration test for the set_hostname module.

This module specify two tests: One updates only the hostname and the other
one updates the hostname and fqdn of the system. For both of these tests
we will check is the changes requested by the user data are being respected
after the system is boot.

(This is ported from
``tests/cloud_tests/testcases/modules/set_hostname.yaml`` and
``tests/cloud_tests/testcases/modules/set_hostname_fqdn.yaml``.)"""

import pytest

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


@pytest.mark.ci
class TestHostname:
    @pytest.mark.user_data(USER_DATA_HOSTNAME)
    def test_hostname(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit2" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN.format(True))
    def test_prefer_fqdn(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit2.test.io" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_PREFER_FQDN.format(False))
    def test_prefer_short_hostname(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit1" in hostname_output.strip()

    @pytest.mark.user_data(USER_DATA_FQDN)
    def test_hostname_and_fqdn(self, client):
        hostname_output = client.execute("hostname")
        assert "cloudinit1" in hostname_output.strip()

        fqdn_output = client.execute("hostname --fqdn")
        assert "cloudinit2.i9n.cloud-init.io" in fqdn_output.strip()

        host_output = client.execute("grep ^127 /etc/hosts")
        assert (
            "127.0.1.1 {} {}".format(fqdn_output, hostname_output)
            in host_output
        )
        assert "127.0.0.1 localhost" in host_output
