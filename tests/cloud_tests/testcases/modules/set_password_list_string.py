# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestPasswordListString(base.PasswordListTest, base.CloudTestCase):
    """Test password setting via string in chpasswd/list."""

    __test__ = True

# vi: ts=4 expandtab
