# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigurePrimary(base.CloudTestCase):
    """Test apt-configure module."""

    def test_ubuntu_sources(self):
        """Test no default Ubuntu entries exist."""
        out = self.get_data_file('sources.list')
        ubuntu_source_count = len(
            [line for line in out.split('\n') if 'archive.ubuntu.com' in line])
        self.assertEqual(0, ubuntu_source_count)

    def test_gatech_sources(self):
        """Test GaTech entries exist."""
        out = self.get_data_file('sources.list')
        gatech_source_count = len(
            [line for line in out.split('\n') if 'gtlib.gatech.edu' in line])
        self.assertGreater(gatech_source_count, 0)

# vi: ts=4 expandtab
