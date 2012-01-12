from unittest import TestCase
from mocker import MockerTestCase

from cloudinit.CloudConfig.cc_ca_certs import handle, write_file

class TestAddCaCerts(MockerTestCase):
    def setUp(self):
        super(TestAddCaCerts, self).setUp()
        self.name = "ca-certs"
        self.cloud_init = None
        self.log = None
        self.args = []

    def test_no_config(self):
        """Test that no certificate are written if not provided."""
        config = {"unknown-key": "value"}

        mock = self.mocker.replace(write_file, passthrough=False)
        self.mocker.replay()

        handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_no_trusted_list(self):
        """Test that no certificate are written if not provided."""
        config = {"ca-certs": {}}

        mock = self.mocker.replace(write_file, passthrough=False)
        self.mocker.replay()

        handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_no_certs_in_list(self):
        """Test that no certificate are written if not provided."""
        config = {"ca-certs": {"trusted": []}}

        mock = self.mocker.replace(write_file, passthrough=False)
        self.mocker.replay()

        handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_single_cert(self):
        """Test adding a single certificate to the trusted CAs"""
        cert = "CERT1\nLINE2\nLINE3"
        config = {"ca-certs": {"trusted": cert}}

        mock = self.mocker.replace(write_file, passthrough=False)
        mock("/usr/share/ca-certificates/cloud-init-provided.crt",
             cert, "root", "root", "644")
        self.mocker.replay()

        handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_multiple_certs(self):
        """Test adding multiple certificate to the trusted CAs"""
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        cert_file = "\n".join(certs)
        config = {"ca-certs": {"trusted": certs}}

        mock = self.mocker.replace(write_file, passthrough=False)
        mock("/usr/share/ca-certificates/cloud-init-provided.crt",
             cert_file, "root", "root", "644")
        self.mocker.replay()

        handle(self.name, config, self.cloud_init, self.log, self.args)
