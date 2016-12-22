# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSshImportId(base.CloudTestCase):
    """Test ssh import id module"""

    def test_authorized_keys(self):
        """Test that ssh keys were imported"""
        out = self.get_data_file('auth_keys_ubuntu')

        # Rather than checking the key fingerprints, you could just check
        # the ending comment for where it got imported from in case these
        # change in the future :\
        self.assertIn('8sXGTYYw3iQSkOvDUUlIsqdaO+w== powersj@github/'
                      '18564351 # ssh-import-id gh:powersj', out)
        self.assertIn('Hj29SCmXp5Kt5/82cD/VN3NtHw== smoser@brickies-'
                      'canonical # ssh-import-id lp:smoser', out)
        self.assertIn('7cUDQSXbabilgnzTjHo9mjd/kZ7cLOHP smoser@bart-'
                      'canonical # ssh-import-id lp:smoser', out)
        self.assertIn('aX0VHGXvHAQlPl4n7+FzAE1UmWFYEGrsSoNvLv3 smose'
                      'r@kaypeah # ssh-import-id lp:smoser', out)

# vi: ts=4 expandtab
