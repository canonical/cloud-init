# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestNtpServers(base.CloudTestCase):
    """Test ntp module"""

    def test_ntp_installed(self):
        """Test ntp installed"""
        out = self.get_data_file('ntp_installed_servers')
        self.assertEqual(0, int(out))

    def test_ntp_dist_entries(self):
        """Test dist config file is empty"""
        out = self.get_data_file('ntp_conf_dist_servers')
        self.assertEqual(0, int(out))

    def test_ntp_entries(self):
        """Test config server entries"""
        out = self.get_data_file('ntp_conf_servers')
        servers = self.cloud_config.get('ntp').get('servers')
        for server in servers:
            self.assertIn('server %s iburst' % server, out)

    def test_ntpq_servers(self):
        """Test ntpq output has configured servers"""
        out = self.get_data_file('ntpq_servers')
        servers = self.cloud_config.get('ntp').get('servers')
        for server in servers:
            self.assertIn(server, out)

# vi: ts=4 expandtab
