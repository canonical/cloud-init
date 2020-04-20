# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptPipeliningOS(base.CloudTestCase):
    """Test apt-pipelining module."""

    def test_os_pipelining(self):
        """test 'os' settings does not write apt config file."""
        out = self.get_data_file('90cloud-init-pipelining_not_written')
        self.assertEqual(0, int(out))

# vi: ts=4 expandtab
