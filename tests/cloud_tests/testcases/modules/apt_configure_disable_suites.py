# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigureDisableSuites(base.CloudTestCase):
    """Test apt-configure module."""

    def test_empty_sourcelist(self):
        """Test source list is empty."""
        out = self.get_data_file('sources.list')
        self.assertEqual('', out)

# vi: ts=4 expandtab
