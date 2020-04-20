# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestInstall(base.CloudTestCase):
    """Example cloud-config test."""

    def test_htop(self):
        """Verify htop installed."""
        out = self.get_data_file('htop')
        self.assertEqual(1, int(out))

    def test_tree(self):
        """Verify tree installed."""
        out = self.get_data_file('treeutils')
        self.assertEqual(1, int(out))

# vi: ts=4 expandtab
