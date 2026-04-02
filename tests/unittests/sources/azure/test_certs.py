# This file is part of cloud-init. See LICENSE file for license information.

import os
from textwrap import dedent

import pytest

from cloudinit import subp
from cloudinit.sources.azure import certs


def _require_commands(*commands):
    """Skip the test if any required external command is unavailable."""
    for command in commands:
        if subp.which(command) is None:
            pytest.skip(f"{command} not available")


@pytest.fixture
def data_file_path():
    """Return a helper that resolves Azure test data file paths."""

    def _path(name):
        return os.path.join("tests", "data", "azure", name)

    return _path


@pytest.fixture
def cert_data(data_file_path):
    """Load the test certificate data, skipping if unavailable."""
    cert_file = data_file_path("pubkey_extract_cert")
    if not os.path.exists(cert_file):
        pytest.skip("Test data file not found")
    with open(cert_file, "r") as f:
        return f.read()


# --- Shared test data ---

_VALID_RSA_KEY = (
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDHU9IDclbKVYVbYuv0+zViX"
    "+wTwlKspslmy/uf3hkWLh7pyzyrq70S7qtSW2EGixUPxZS/R8pOLHoinlKF9ILgj"
    "0gVTCJsSwnWpXRg3rhZwIVoYMHN50BHS1SqVD0lsWNMXmo76LoJcjmWvwIznvj5C"
    "/gnhU+K7+c3m7AlCyU2wjwpBAEYj7PQs6l/wTqpEiaqC5NytNBd7qp+lYYysVrpa"
    "1PFL0Nj4MMZARIfjkiJtL9qDhy9YZeJRQ6q/Fhz0kjvkZnfxixfKF4yWzOfhBrAt"
    "pF6oOnuYKk3hxjh9KjTTX4/U8zdLojalX09iyHyEjwJKGlGEpzh1aY7t5btUyvp"
)

_VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6U"
    "Orhxd+wTwlKspslmy/uf user@host"
)

_VALID_ECDSA_KEY = (
    "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAI"
    "bmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87u"
    "RFNngSmOjp2S185mF user@host"
)

_INVALID_X509_CERT = (
    "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
)

_X509_CERT = dedent(
    """\
    -----BEGIN CERTIFICATE-----
    MIIB+TCCAeOgAwIBAgIBATANBgkqhkiG9w0BAQUFADAWMRQwEgYDVQQDDAtSb290
    -----END CERTIFICATE-----
    """
)


class TestIsOpensshFormatted:
    """Test is_openssh_formatted() function."""

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param(_VALID_RSA_KEY, id="rsa-without-comment"),
            pytest.param(_VALID_ED25519_KEY, id="ed25519"),
            pytest.param(_VALID_ECDSA_KEY, id="ecdsa"),
            pytest.param(
                "ssh-rsa AAAAB3NzaC1yc2EAAAA\r\nBBBB user@host",
                id="windows-line-endings",
            ),
        ],
    )
    def test_valid(self, key):
        """Valid OpenSSH keys should return True."""
        assert certs.is_openssh_formatted(key) is True

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(_X509_CERT, id="x509-certificate"),
            pytest.param("", id="empty-string"),
            pytest.param("this is not a key", id="random-string"),
            pytest.param(
                "not-a-key-type AAAAB3NzaC1yc2EAAAADAQABAAABAQ",
                id="malformed-key-type",
            ),
        ],
    )
    def test_invalid(self, value):
        """Non-OpenSSH strings should return False."""
        assert certs.is_openssh_formatted(value) is False


class TestSanitizeOpensshKey:
    """Test sanitize_openssh_key() function."""

    @pytest.mark.parametrize(
        "key, expected",
        [
            pytest.param(
                "ssh-rsa AAAA\r\nBBBB user@host",
                "ssh-rsa AAAABBBB user@host",
                id="removes-embedded-crlf",
            ),
            pytest.param(
                "ssh-rsa AAAABBBB user@host\r\n",
                "ssh-rsa AAAABBBB user@host",
                id="strips-trailing-crlf",
            ),
            pytest.param(
                "ssh-rsa AAAABBBB user@host",
                "ssh-rsa AAAABBBB user@host",
                id="clean-key-unchanged",
            ),
            pytest.param(
                "ssh-rsa AA\r\nAA\r\nBBBB user@host",
                "ssh-rsa AAAABBBB user@host",
                id="multiple-crlf-sequences",
            ),
        ],
    )
    def test_sanitize(self, key, expected):
        """Sanitized keys should have CRLF sequences removed."""
        assert certs.sanitize_openssh_key(key) == expected


class TestIsX509Certificate:
    """Test is_x509_certificate() function."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(_VALID_RSA_KEY, id="openssh-key"),
            pytest.param("", id="empty-string"),
            pytest.param("this is not a certificate", id="random-string"),
            pytest.param(
                "-----BEGIN CERTIFICATE-----", id="only-begin-marker"
            ),
            pytest.param("-----END CERTIFICATE-----", id="only-end-marker"),
        ],
    )
    def test_invalid(self, value):
        """Non-certificate inputs should return False."""
        assert certs.is_x509_certificate(value) is False

    def test_invalid_certificate_content(self, monkeypatch):
        """Certificate with invalid content should return False."""

        def _raise(*args, **kwargs):
            raise subp.ProcessExecutionError("unable to load certificate")

        monkeypatch.setattr("cloudinit.sources.azure.certs.subp.subp", _raise)
        assert certs.is_x509_certificate(_INVALID_X509_CERT) is False

    @pytest.mark.allow_subp_for("openssl")
    def test_valid_certificate_integration(self, cert_data):
        """Integration test: Actually validate certificate with openssl."""
        _require_commands("openssl")
        assert certs.is_x509_certificate(cert_data) is True

    @pytest.mark.allow_subp_for("openssl")
    def test_certificate_with_extra_whitespace_integration(self, cert_data):
        """Integration test: Certificate with extra whitespace validates."""
        _require_commands("openssl")
        assert certs.is_x509_certificate("\n\n" + cert_data + "\n\n") is True

    @pytest.mark.allow_subp_for("openssl")
    def test_invalid_certificate_integration(self):
        """Integration test: Reject invalid certificate with real openssl."""
        _require_commands("openssl")
        assert certs.is_x509_certificate(_INVALID_X509_CERT) is False


class TestExtractX509Certificates:
    """Test extract_x509_certificates() function."""

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param("", id="empty-string"),
            pytest.param(None, id="none"),
            pytest.param(
                "this is just some random text\nwith no certificate",
                id="no-cert-markers",
            ),
        ],
    )
    def test_returns_empty_list(self, data):
        """Data with no certificates should return empty list."""
        assert certs.extract_x509_certificates(data) == []

    def test_extracts_all_valid_certificates(self, monkeypatch):
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

        monkeypatch.setattr(
            "cloudinit.sources.azure.certs.is_x509_certificate",
            lambda cert: True,
        )

        result = certs.extract_x509_certificates(bundle)

        assert len(result) == 2
        assert "CERT1DATA" in result[0]
        assert "CERT2DATA" in result[1]

    def test_skips_private_keys(self, monkeypatch):
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

        monkeypatch.setattr(
            "cloudinit.sources.azure.certs.is_x509_certificate",
            lambda cert: True,
        )

        result = certs.extract_x509_certificates(bundle)

        assert len(result) == 1
        assert "CERTDATA" in result[0]
        assert "PRIVATEKEYDATA" not in result[0]

    def test_skips_invalid_certs(self, monkeypatch):
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

        results = iter([False, True])
        monkeypatch.setattr(
            "cloudinit.sources.azure.certs.is_x509_certificate",
            lambda cert: next(results),
        )

        result = certs.extract_x509_certificates(bundle)

        assert len(result) == 1
        assert "VALID" in result[0]

    @pytest.mark.allow_subp_for("openssl")
    def test_extraction_from_mixed_bundle_integration(self, cert_data):
        """Integration test: Extract cert from bundle with private key."""
        _require_commands("openssl")

        private_key = dedent(
            """\
            -----BEGIN PRIVATE KEY-----
            MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDExample
            -----END PRIVATE KEY-----
            """
        )
        bundle = private_key + "\n" + cert_data

        result = certs.extract_x509_certificates(bundle)

        assert len(result) == 1
        assert "-----BEGIN CERTIFICATE-----" in result[0]
        assert "PRIVATE KEY" not in result[0]


class TestConvertX509ToOpenssh:
    """Test convert_x509_to_openssh() function."""

    def test_conversion_calls_correct_commands(self, monkeypatch):
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

        calls = []

        def mock_subp(cmd, data=None, **kwargs):
            calls.append((cmd, data))
            if cmd[0] == "openssl":
                return (pubkey, "")
            return (expected_ssh_key, "")

        monkeypatch.setattr(
            "cloudinit.sources.azure.certs.subp.subp", mock_subp
        )

        result = certs.convert_x509_to_openssh(cert)

        assert result == expected_ssh_key
        assert len(calls) == 2
        assert calls[0][0] == ["openssl", "x509", "-noout", "-pubkey"]
        assert calls[0][1] == cert
        assert calls[1][0] == [
            "ssh-keygen",
            "-i",
            "-m",
            "PKCS8",
            "-f",
            "/dev/stdin",
        ]
        assert calls[1][1] == pubkey

    def test_openssl_failure_raises_exception(self, monkeypatch):
        """Test that openssl failure raises ProcessExecutionError."""
        cert = (
            "-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----"
        )

        def _raise(*args, **kwargs):
            raise subp.ProcessExecutionError("openssl failed")

        monkeypatch.setattr("cloudinit.sources.azure.certs.subp.subp", _raise)

        with pytest.raises(subp.ProcessExecutionError, match="openssl failed"):
            certs.convert_x509_to_openssh(cert)

    def test_ssh_keygen_failure_raises_exception(self, monkeypatch):
        """Test that ssh-keygen failure raises ProcessExecutionError."""
        cert = "-----BEGIN CERTIFICATE-----\nVALID\n-----END CERTIFICATE-----"
        pubkey = (
            "-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----"
        )

        call_count = 0

        def mock_subp(cmd, data=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (pubkey, "")
            raise subp.ProcessExecutionError("ssh-keygen failed")

        monkeypatch.setattr(
            "cloudinit.sources.azure.certs.subp.subp", mock_subp
        )

        with pytest.raises(
            subp.ProcessExecutionError, match="ssh-keygen failed"
        ):
            certs.convert_x509_to_openssh(cert)

    @pytest.mark.allow_subp_for("openssl", "ssh-keygen")
    def test_conversion_integration(self, cert_data, data_file_path):
        """Integration test: Convert certificate with real commands."""
        _require_commands("openssl", "ssh-keygen")
        key_file = data_file_path("pubkey_extract_ssh_key")

        if not os.path.exists(key_file):
            pytest.skip("Test data files not found")

        with open(key_file, "r") as f:
            expected_key = f.read().strip()

        result = certs.convert_x509_to_openssh(cert_data)
        assert result.strip() == expected_key
