# This file is part of cloud-init. See LICENSE file for license information.

import shutil
from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.sources.azure import certs


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

    def test_key_with_crlf_passes_parser(self):
        r"""Keys with embedded CRLF (\r\n) pass the parser.

        The parser's split(None, 2) treats \r\n as whitespace, so
        is_openssh_formatted alone will accept the key. Callers must
        use sanitize_openssh_key() first to strip CRLF sequences.
        """
        key = "ssh-rsa AAAAB3NzaC1yc2EAAAA\r\nBBBB user@host"
        assert certs.is_openssh_formatted(key) is True

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


class TestSanitizeOpensshKey:
    """Test sanitize_openssh_key() function."""

    def test_strips_crlf_sequences(self):
        r"""Embedded CRLF (\r\n) sequences should be removed."""
        key = "ssh-rsa AAAAB3NzaC1yc2EAAAA\r\nBBBB user@host"
        result = certs.sanitize_openssh_key(key)
        assert "\r\n" not in result
        assert result == "ssh-rsa AAAAB3NzaC1yc2EAAAABBBB user@host"

    def test_key_without_crlf_unchanged(self):
        """Keys without CRLF should be returned unchanged (stripped)."""
        key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQAB user@host"
        assert certs.sanitize_openssh_key(key) == key

    def test_strips_surrounding_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        key = "  ssh-rsa AAAAB3NzaC1yc2EAAAADAQAB user@host  "
        assert certs.sanitize_openssh_key(key) == key.strip()


class TestIsX509Certificate:
    """Test is_x509_certificate() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return Path("tests", "data", "azure", name)

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
        m_subp.assert_called_once()

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_valid_certificate_integration(self):
        """Integration test: Actually validate certificate with openssl."""
        cert_file = self._data_file_path("pubkey_extract_cert")

        if not cert_file.exists():
            pytest.skip("Test data file not found")

        cert = cert_file.read_text()

        assert certs.is_x509_certificate(cert) is True

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_certificate_with_extra_whitespace_integration(self):
        """Integration test: Certificate with extra whitespace validates."""
        cert_file = self._data_file_path("pubkey_extract_cert")

        if not cert_file.exists():
            pytest.skip("Test data file not found")

        cert = cert_file.read_text()

        # Add extra whitespace
        cert = "\n\n" + cert + "\n\n"

        # Actually calls openssl to validate
        assert certs.is_x509_certificate(cert) is True

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_invalid_certificate_integration(self):
        """Integration test: Reject invalid certificate with real openssl."""
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )

        # Actually calls openssl, which will fail on invalid cert
        assert certs.is_x509_certificate(cert) is False


class TestExtractX509Certificates:
    """Test extract_x509_certificates() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return Path("tests", "data", "azure", name)

    def test_no_certificate_returns_empty_list(self):
        """Data with no certificate should return empty list."""
        data = "this is just some random text\nwith no certificate"
        assert certs.extract_x509_certificates(data) == []

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_extracts_all_valid_certificates(self, m_is_x509):
        """Should extract and return all valid certificates."""
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

        m_is_x509.return_value = True

        result = certs.extract_x509_certificates(bundle)

        assert result == [cert1.strip(), cert2.strip()]

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

        result = certs.extract_x509_certificates(bundle)

        assert result == [certificate.strip()]

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_skips_invalid_certs(self, m_is_x509):
        """Should skip invalid cert and return only valid ones."""
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

        m_is_x509.side_effect = [False, True]

        result = certs.extract_x509_certificates(bundle)

        assert result == [valid_cert.strip()]

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_empty_data_returns_empty_list(self, m_is_x509):
        """Empty data should return empty list."""
        assert certs.extract_x509_certificates("") == []
        assert certs.extract_x509_certificates(None) == []
        m_is_x509.assert_not_called()

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_extraction_from_mixed_bundle_integration(self):
        """Integration test: Extract cert from bundle with private key."""
        cert_file = self._data_file_path("pubkey_extract_cert")

        if not cert_file.exists():
            pytest.skip("Test data file not found")

        cert = cert_file.read_text()

        private_key = dedent(
            """\
            -----BEGIN PRIVATE KEY-----
            MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDExample
            -----END PRIVATE KEY-----
            """
        )
        bundle = private_key + "\n" + cert

        result = certs.extract_x509_certificates(bundle)

        assert result == [cert.strip()]


class TestConvertX509ToOpenssh:
    """Test convert_x509_to_openssh() function."""

    def _data_file_path(self, name):
        """Helper to get path to test data file."""
        return Path("tests", "data", "azure", name)

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

    @pytest.mark.skipif(
        shutil.which("openssl") is None or shutil.which("ssh-keygen") is None,
        reason="openssl or ssh-keygen not available",
    )
    @pytest.mark.allow_subp_for("openssl", "ssh-keygen")
    def test_conversion_integration(self):
        """Integration test: Convert certificate with real commands."""
        cert_file = self._data_file_path("pubkey_extract_cert")
        key_file = self._data_file_path("pubkey_extract_ssh_key")

        if not cert_file.exists() or not key_file.exists():
            pytest.skip("Test data files not found")

        cert = cert_file.read_text()
        expected_key = key_file.read_text().strip()

        # Convert and compare
        result = certs.convert_x509_to_openssh(cert)
        assert result.strip() == expected_key
