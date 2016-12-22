# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestWriteFiles(base.CloudTestCase):
    """Example cloud-config test"""

    def test_b64(self):
        """Test b64 encoded file reads as ascii"""
        out = self.get_data_file('file_b64')
        self.assertIn('ASCII text', out)

    def test_binary(self):
        """Test binary file reads as executable"""
        out = self.get_data_file('file_binary')
        self.assertIn('ELF 64-bit LSB executable, x86-64, version 1', out)

    def test_gzip(self):
        """Test gzip file shows up as a shell script"""
        out = self.get_data_file('file_gzip')
        self.assertIn('POSIX shell script, ASCII text executable', out)

    def test_text(self):
        """Test text shows up as ASCII text"""
        out = self.get_data_file('file_text')
        self.assertIn('ASCII text', out)

# vi: ts=4 expandtab
