# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestCaCerts(base.CloudTestCase):
    """Test ca certs module."""

    def test_certs_updated(self):
        """Test certs have been updated in /etc/ssl/certs."""
        out = self.get_data_file('cert_links')
        # Bionic update-ca-certificates creates less links debian #895075
        unlinked_files = []
        links = {}
        for cert_line in out.splitlines():
            if '->' in cert_line:
                fname, _sep, link = cert_line.split()
                links[fname] = link
            else:
                unlinked_files.append(cert_line)
        self.assertEqual(['ca-certificates.crt'], unlinked_files)
        self.assertEqual('cloud-init-ca-certs.pem', links['a535c1f3.0'])
        self.assertEqual(
            '/usr/share/ca-certificates/cloud-init-ca-certs.crt',
            links['cloud-init-ca-certs.pem'])

    def test_cert_installed(self):
        """Test line from our cert exists."""
        out = self.get_data_file('cert')
        self.assertIn('a36c744454555024e7f82edc420fd2c8', out)

# vi: ts=4 expandtab
