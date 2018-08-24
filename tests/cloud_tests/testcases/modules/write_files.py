# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestWriteFiles(base.CloudTestCase):
    """Example cloud-config test."""

    def test_b64(self):
        """Test b64 encoded file reads as ascii."""
        out = self.get_data_file('file_b64')
        self.assertIn('ASCII text', out)

    def test_binary(self):
        """Test binary file reads as executable."""
        out = self.get_data_file('file_binary').strip()
        md5 = "3801184b97bb8c6e63fa0e1eae2920d7"
        sha256 = ("2c791c4037ea5bd7e928d6a87380f8ba7a803cd83d"
                  "5e4f269e28f5090f0f2c9a")
        self.assertIn(out, (md5 + "  -", sha256 + "  -"))

    def test_gzip(self):
        """Test gzip file shows up as a shell script."""
        out = self.get_data_file('file_gzip')
        self.assertIn('POSIX shell script, ASCII text executable', out)

    def test_text(self):
        """Test text shows up as ASCII text."""
        out = self.get_data_file('file_text')
        self.assertIn('ASCII text', out)

# vi: ts=4 expandtab
