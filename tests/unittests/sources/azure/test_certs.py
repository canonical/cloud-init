# This file is part of cloud-init. See LICENSE file for license information.

import os
from textwrap import dedent
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.sources.azure import certs


def _require_commands(*commands):
    """Skip the test if any required external command is unavailable."""
    for command in commands:
        if subp.which(command) is None:
            pytest.skip(f"{command} not available")


class TestIsOpensshFormatted:
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
        r"""Keys with Windows line endings (\\r\\n) should return False."""
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
        key = "not-a-key-type AAAAB3NzaC1yc2EAAAADAQABAAABAQ"
        assert certs.is_openssh_formatted(key) is False


class TestIsX509Certificate:
    """Test is_x509_certificate() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return os.path.join("tests", "data", "azure", name)

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

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_invalid_certificate_content(self, m_subp):
        """Certificate with invalid content should return False."""
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )

        # Mock openssl failure for invalid certificate
        m_subp.side_effect = subp.ProcessExecutionError(
            "unable to load certificate"
        )

        assert certs.is_x509_certificate(cert) is False

    @pytest.mark.allow_subp_for("openssl")
    def test_valid_certificate_integration(self):
        """Integration test: Actually validate certificate with openssl."""
        _require_commands("openssl")
        cert_file = self._data_file_path("pubkey_extract_cert")

        # Skip if test data file doesn't exist
        if not os.path.exists(cert_file):
            pytest.skip("Test data file not found")

        with open(cert_file, "r") as f:
            cert = f.read()

        # Actually calls openssl to validate
        assert certs.is_x509_certificate(cert) is True

    @pytest.mark.allow_subp_for("openssl")
    def test_certificate_with_extra_whitespace_integration(self):
        """Integration test: Certificate with extra whitespace validates."""
        _require_commands("openssl")
        cert_file = self._data_file_path("pubkey_extract_cert")

        # Skip if test data file doesn't exist
        if not os.path.exists(cert_file):
            pytest.skip("Test data file not found")

        with open(cert_file, "r") as f:
            cert = f.read()

        # Add extra whitespace
        cert = "\n\n" + cert + "\n\n"

        # Actually calls openssl to validate
        assert certs.is_x509_certificate(cert) is True

    @pytest.mark.allow_subp_for("openssl")
    def test_invalid_certificate_integration(self):
        """Integration test: Reject invalid certificate with real openssl."""
        _require_commands("openssl")
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )

        # Actually calls openssl, which will fail on invalid cert
        assert certs.is_x509_certificate(cert) is False


class TestExtractX509Certificate:
    """Test extract_x509_certificate() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return os.path.join("tests", "data", "azure", name)

    def test_no_certificate_returns_none(self):
        """Data with no certificate should return None."""
        data = "this is just some random text\nwith no certificate"
        assert certs.extract_x509_certificate(data) is None

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_extracts_first_valid_certificate(self, m_is_x509):
        """Should extract and return the first valid certificate."""
        cert1 = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            CERT1DATA
            -----END CERTIFICATE-----
            """
        )
        cert2 = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            CERT2DATA
            -----END CERTIFICATE-----
            """
        )
        bundle = cert1 + "\n" + cert2

        # Mock validation to accept cert1
        m_is_x509.return_value = True

        result = certs.extract_x509_certificate(bundle)

        # Should return first cert
        assert result is not None
        assert "CERT1DATA" in result
        assert "CERT2DATA" not in result

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_skips_private_keys(self, m_is_x509):
        """Should skip private keys and extract certificate."""
        private_key = dedent(
            """\
            -----BEGIN PRIVATE KEY-----
            PRIVATEKEYDATA
            -----END PRIVATE KEY-----
            """
        )
        certificate = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            CERTDATA
            -----END CERTIFICATE-----
            """
        )
        bundle = private_key + "\n" + certificate

        m_is_x509.return_value = True

        result = certs.extract_x509_certificate(bundle)

        assert result is not None
        assert "CERTDATA" in result
        assert "PRIVATEKEYDATA" not in result

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_returns_first_valid_cert_after_invalid(self, m_is_x509):
        """Should skip invalid cert and return next valid one."""
        invalid_cert = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            INVALID
            -----END CERTIFICATE-----
            """
        )
        valid_cert = dedent(
            """\
            -----BEGIN CERTIFICATE-----
            VALID
            -----END CERTIFICATE-----
            """
        )
        bundle = invalid_cert + "\n" + valid_cert

        # First call returns False (invalid), second returns True (valid)
        m_is_x509.side_effect = [False, True]

        result = certs.extract_x509_certificate(bundle)

        assert result is not None
        assert "VALID" in result
        assert "INVALID" not in result

    @pytest.mark.allow_subp_for("openssl")
    def test_extraction_from_mixed_bundle_integration(self):
        """Integration test: Extract cert from bundle with private key."""
        _require_commands("openssl")
        cert_file = self._data_file_path("pubkey_extract_cert")

        # Skip if test data file doesn't exist
        if not os.path.exists(cert_file):
            pytest.skip("Test data file not found")

        with open(cert_file, "r") as f:
            cert = f.read()

        # Create a bundle with a private key and certificate
        private_key = dedent(
            """\
            -----BEGIN PRIVATE KEY-----
            MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDExample
            -----END PRIVATE KEY-----
            """
        )
        bundle = private_key + "\n" + cert

        result = certs.extract_x509_certificate(bundle)

        # Should extract the valid certificate, not the private key
        assert result is not None
        assert "-----BEGIN CERTIFICATE-----" in result
        assert "PRIVATE KEY" not in result


class TestConvertX509ToOpenssh:
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

    @pytest.mark.allow_subp_for("openssl", "ssh-keygen")
    def test_conversion_integration(self):
        """Integration test: Convert certificate with real commands."""
        _require_commands("openssl", "ssh-keygen")
        cert_file = self._data_file_path("pubkey_extract_cert")
        key_file = self._data_file_path("pubkey_extract_ssh_key")

        # Skip if test data files don't exist
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            pytest.skip("Test data files not found")

        # Load test data
        with open(cert_file, "r") as f:
            cert = f.read()
        with open(key_file, "r") as f:
            expected_key = f.read().strip()

        # Convert and compare
        result = certs.convert_x509_to_openssh(cert)
        assert result.strip() == expected_key
