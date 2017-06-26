# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestNtpPools(base.CloudTestCase):
    """Test ntp module."""

    def test_ntp_installed(self):
        """Test ntp installed"""
        out = self.get_data_file('ntp_installed_pools')
        self.assertEqual(0, int(out))

    def test_ntp_dist_entries(self):
        """Test dist config file is empty"""
        out = self.get_data_file('ntp_conf_dist_pools')
        self.assertEqual(0, int(out))

    def test_ntp_entires(self):
        """Test config entries"""
        out = self.get_data_file('ntp_conf_pools')
        pools = self.cloud_config.get('ntp').get('pools')
        for pool in pools:
            self.assertIn('pool %s iburst' % pool, out)

    def test_ntpq_servers(self):
        """Test ntpq output has configured servers"""
        out = self.get_data_file('ntpq_servers')
        pools = self.cloud_config.get('ntp').get('pools')
        for pool in pools:
            self.assertIn(pool, out)

# vi: ts=4 expandtab
