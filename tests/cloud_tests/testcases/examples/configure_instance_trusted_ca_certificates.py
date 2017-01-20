# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestTrustedCA(base.CloudTestCase):
    """Example cloud-config test"""

    def test_cert_count_ca(self):
        """Test correct count of CAs in .crt"""
        out = self.get_data_file('cert_count_ca')
        self.assertIn('7 /etc/ssl/certs/ca-certificates.crt', out)

    def test_cert_count_cloudinit(self):
        """Test correct count of CAs in .pem"""
        out = self.get_data_file('cert_count_cloudinit')
        self.assertIn('7 /etc/ssl/certs/cloud-init-ca-certs.pem', out)

    def test_cloudinit_certs(self):
        """Test text of cert"""
        out = self.get_data_file('cloudinit_certs')
        self.assertIn('-----BEGIN CERTIFICATE-----', out)
        self.assertIn('YOUR-ORGS-TRUSTED-CA-CERT-HERE', out)
        self.assertIn('-----END CERTIFICATE-----', out)

# vi: ts=4 expandtab
