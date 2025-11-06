# This file is part of cloud-init. See LICENSE file for license information.

import os
from textwrap import dedent
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.sources.azure import certs
from tests.unittests.helpers import CiTestCase


class TestIsOpensshFormatted(CiTestCase):
    """Test is_openssh_formatted() function."""

    def test_valid_rsa_key_without_comment(self):
        """Valid ssh-rsa key without comment should return True."""
        key = (
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDHU9IDclbKVYVbYuv0+zViX"
            "+wTwlKspslmy/uf3hkWLh7pyzyrq70S7qtSW2EGixUPxZS/R8pOLHoinlKF9ILgj"
            "0gVTCJsSwnWpXRg3rhZwIVoYMHN50BHS1SqVD0lsWNMXmo76LoJcjmWvwIznvj5C"
            "/gnhU+K7+c3m7AlCyU2wjwpBAEYj7PQs6l/wTqpEiaqC5NytNBd7qp+lYYysVrpa"
            "1PFL0Nj4MMZARIfjkiJtL9qDhy9YZeJRQ6q/Fhz0kjvkZnfxixfKF4yWzOfhBrAt"
            "pF6oOnuYKk3hxjh9KjTTX4/U8zdLojalX09iyHyEjwJKGlGEpzh1aY7t5btUyvp"
        )
        assert certs.is_openssh_formatted(key) is True

    def test_valid_ed25519_key(self):
        """Valid ssh-ed25519 key should return True."""
        key = (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6U"
            "Orhxd+wTwlKspslmy/uf user@host"
        )
        assert certs.is_openssh_formatted(key) is True

    def test_valid_ecdsa_key(self):
        """Valid ecdsa-sha2-nistp256 key should return True."""
        key = (
            "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAI"
            "bmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87u"
            "RFNngSmOjp2S185mF user@host"
        )
        assert certs.is_openssh_formatted(key) is True

    def test_key_with_windows_line_endings(self):
        """Keys with Windows line endings (\\r\\n) should return False."""
        key = "ssh-rsa AAAAB3NzaC1yc2EAAAA\r\nBBBB user@host"
        assert certs.is_openssh_formatted(key) is False

    def test_x509_certificate_returns_false(self):
        """x509 certificates are not OpenSSH formatted."""
        cert = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            MIIB+TCCAeOgAwIBAgIBATANBgkqhkiG9w0BAQUFADAWMRQwEgYDVQQDDAtSb290
            -----END CERTIFICATE-----
            """
        )
        assert certs.is_openssh_formatted(cert) is False

    def test_empty_string(self):
        """Empty string should return False."""
        assert certs.is_openssh_formatted("") is False

    def test_random_string(self):
        """Random non-key string should return False."""
        assert certs.is_openssh_formatted("this is not a key") is False

    def test_malformed_key(self):
        """Malformed key should return False."""
        key = "ssh-rsa NOTBASE64!@#$%"
        assert certs.is_openssh_formatted(key) is False


class TestIsX509Certificate(CiTestCase):
    """Test is_x509_certificate() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return os.path.join("tests", "data", "azure", name)

    def test_valid_certificate(self):
        """Valid x509 certificate should return True."""
        cert_file = self._data_file_path("pubkey_extract_cert")

        # Skip if test data file doesn't exist or openssl not available
        if not os.path.exists(cert_file):
            pytest.skip("Test data file not found")
        try:
            subp.which("openssl")
        except subp.ProcessExecutionError:
            pytest.skip("openssl not available")

        with open(cert_file, "r") as f:
            cert = f.read()

        assert certs.is_x509_certificate(cert) is True

    def test_certificate_with_extra_whitespace(self):
        """Certificate with extra whitespace should return True."""
        cert_file = self._data_file_path("pubkey_extract_cert")

        # Skip if test data file doesn't exist or openssl not available
        if not os.path.exists(cert_file):
            pytest.skip("Test data file not found")
        try:
            subp.which("openssl")
        except subp.ProcessExecutionError:
            pytest.skip("openssl not available")

        with open(cert_file, "r") as f:
            cert = f.read()

        # Add extra whitespace
        cert = "\n\n" + cert + "\n\n"
        assert certs.is_x509_certificate(cert) is True

    def test_openssh_key_returns_false(self):
        """OpenSSH keys should return False."""
        key = (
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDHU9IDclbKVYVbYuv0+zViX"
            "+wTwlKspslmy/uf3hkWLh7pyzyrq70S7qtSW2EGixUPxZS/R8pOLHoinlKF9ILgj"
        )
        assert certs.is_x509_certificate(key) is False

    def test_empty_string(self):
        """Empty string should return False."""
        assert certs.is_x509_certificate("") is False

    def test_random_string(self):
        """Random string should return False."""
        assert certs.is_x509_certificate("this is not a certificate") is False

    def test_only_begin_marker(self):
        """Only BEGIN marker should return False."""
        cert = "-----BEGIN CERTIFICATE-----"
        assert certs.is_x509_certificate(cert) is False

    def test_only_end_marker(self):
        """Only END marker should return False."""
        cert = "-----END CERTIFICATE-----"
        assert certs.is_x509_certificate(cert) is False

    def test_invalid_certificate_content(self):
        """Certificate with invalid content should return False."""
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )
        assert certs.is_x509_certificate(cert) is False


class TestConvertX509ToOpenssh(CiTestCase):
    """Test convert_x509_to_openssh() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return os.path.join("tests", "data", "azure", name)

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_conversion_with_mocked_commands(self, m_subp):
        """Test basic conversion flow with mocked subp calls."""
        cert = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            MIIB+TCCAeOgAwIBAgIBATANBgkqhkiG9w0BAQUFADAWMRQwEgYDVQQDDAtSb290
            -----END CERTIFICATE-----
            """
        )
        pubkey = (
            "-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----"
        )
        expected_ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ..."

        # Mock the subp calls: first for openssl, second for ssh-keygen
        m_subp.side_effect = [
            (pubkey, ""),  # openssl x509 -noout -pubkey
            (expected_ssh_key, ""),  # ssh-keygen -i -m PKCS8
        ]

        result = certs.convert_x509_to_openssh(cert)

        assert result == expected_ssh_key
        assert m_subp.call_count == 2

        # Verify openssl command
        openssl_call = m_subp.call_args_list[0]
        assert openssl_call[0][0] == ["openssl", "x509", "-noout", "-pubkey"]
        assert openssl_call[1]["data"] == cert

        # Verify ssh-keygen command
        keygen_call = m_subp.call_args_list[1]
        assert keygen_call[0][0] == [
            "ssh-keygen",
            "-i",
            "-m",
            "PKCS8",
            "-f",
            "/dev/stdin",
        ]
        assert keygen_call[1]["data"] == pubkey

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_openssl_failure_raises_exception(self, m_subp):
        """Test that openssl failure raises ProcessExecutionError."""
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )

        m_subp.side_effect = subp.ProcessExecutionError("openssl failed")

        with pytest.raises(subp.ProcessExecutionError) as exc_info:
            certs.convert_x509_to_openssh(cert)

        assert "openssl failed" in str(exc_info.value)

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_ssh_keygen_failure_raises_exception(self, m_subp):
        """Test that ssh-keygen failure raises ProcessExecutionError."""
        cert = "-----BEGIN CERTIFICATE-----\nVALID\n-----END CERTIFICATE-----"
        pubkey = (
            "-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----"
        )

        # First call (openssl) succeeds, second call (ssh-keygen) fails
        m_subp.side_effect = [
            (pubkey, ""),
            subp.ProcessExecutionError("ssh-keygen failed"),
        ]

        with pytest.raises(subp.ProcessExecutionError) as exc_info:
            certs.convert_x509_to_openssh(cert)

        assert "ssh-keygen failed" in str(exc_info.value)

    def test_conversion_with_real_test_data(self):
        """Test conversion using actual test certificate data.

        This test uses real openssl/ssh-keygen if available, otherwise skips.
        """
        cert_file = self._data_file_path("pubkey_extract_cert")
        key_file = self._data_file_path("pubkey_extract_ssh_key")

        # Skip if test data files don't exist
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            pytest.skip("Test data files not found")

        # Skip if openssl or ssh-keygen not available
        try:
            subp.which("openssl")
            subp.which("ssh-keygen")
        except subp.ProcessExecutionError:
            pytest.skip("openssl or ssh-keygen not available")

        # Load test data
        with open(cert_file, "r") as f:
            cert = f.read()
        with open(key_file, "r") as f:
            expected_key = f.read().strip()

        # Convert and compare
        result = certs.convert_x509_to_openssh(cert)
        assert result.strip() == expected_key
