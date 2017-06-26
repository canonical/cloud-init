# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestSshImportId(base.CloudTestCase):
    """Test ssh import id module."""

    def test_authorized_keys(self):
        """Test that ssh keys were imported."""
        out = self.get_data_file('auth_keys_ubuntu')

        self.assertIn('# ssh-import-id gh:powersj', out)
        self.assertIn('# ssh-import-id lp:smoser', out)

# vi: ts=4 expandtab
