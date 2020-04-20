# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigureSourcesList(base.CloudTestCase):
    """Test apt-configure module."""

    def test_sources_list(self):
        """Test sources.list includes sources."""
        out = self.get_data_file('sources.list')

        # Verify we have 6 entires
        self.assertEqual(6, len(out.rstrip().split('\n')))

        # Verify the keys generated the list correctly
        self.assertRegex(out, r'deb http:\/\/archive.ubuntu.com\/ubuntu '
                         '[a-z].* main restricted')
        self.assertRegex(out, r'deb-src http:\/\/archive.ubuntu.com\/ubuntu '
                         '[a-z].* main restricted')
        self.assertRegex(out, r'deb http:\/\/archive.ubuntu.com\/ubuntu '
                         '[a-z].* universe restricted')
        self.assertRegex(out, r'deb-src http:\/\/archive.ubuntu.com\/ubuntu '
                         '[a-z].* universe restricted')
        self.assertRegex(out, r'deb http:\/\/security.ubuntu.com\/ubuntu '
                         '[a-z].*security multiverse')
        self.assertRegex(out, r'deb-src http:\/\/security.ubuntu.com\/ubuntu '
                         '[a-z].*security multiverse')

# vi: ts=4 expandtab
