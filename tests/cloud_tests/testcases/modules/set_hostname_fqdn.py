# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests import CI_DOMAIN
from tests.cloud_tests.testcases import base


class TestHostnameFqdn(base.CloudTestCase):
    """Test Hostname module."""

    ex_hostname = "cloudinit1"
    ex_fqdn = "cloudinit2." + CI_DOMAIN

    def test_hostname(self):
        """Test hostname output."""
        out = self.get_data_file('hostname')
        self.assertIn(self.ex_hostname, out)

    def test_hostname_fqdn(self):
        """Test hostname fqdn output."""
        out = self.get_data_file('fqdn')
        self.assertIn(self.ex_fqdn, out)

    def test_hosts(self):
        """Test /etc/hosts file."""
        out = self.get_data_file('hosts')
        self.assertIn('127.0.1.1 %s %s' % (self.ex_fqdn, self.ex_hostname),
                      out)
        self.assertIn('127.0.0.1 localhost', out)

# vi: ts=4 expandtab
