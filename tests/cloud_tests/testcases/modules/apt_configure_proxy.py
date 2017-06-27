# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigureProxy(base.CloudTestCase):
    """Test apt-configure module."""

    def test_proxy_config(self):
        """Test proxy options added to apt config."""
        out = self.get_data_file('90cloud-init-aptproxy')
        self.assertIn(
            'Acquire::http::Proxy "http://squid.internal:3128";', out)
        self.assertIn(
            'Acquire::http::Proxy "http://squid.internal:3128";', out)
        self.assertIn(
            'Acquire::ftp::Proxy "ftp://squid.internal:3128";', out)
        self.assertIn(
            'Acquire::https::Proxy "https://squid.internal:3128";', out)

# vi: ts=4 expandtab
