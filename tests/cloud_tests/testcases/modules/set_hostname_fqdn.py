# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestHostnameFqdn(base.CloudTestCase):
    """Test Hostname module"""

    def test_hostname(self):
        """Test hostname output"""
        out = self.get_data_file('hostname')
        self.assertIn('myhostname', out)

    def test_hostname_fqdn(self):
        """Test hostname fqdn output"""
        out = self.get_data_file('fqdn')
        self.assertIn('host.myorg.com', out)

    def test_hosts(self):
        """Test /etc/hosts file"""
        out = self.get_data_file('hosts')
        self.assertIn('127.0.1.1 host.myorg.com myhostname', out)
        self.assertIn('127.0.0.1 localhost', out)

# vi: ts=4 expandtab
