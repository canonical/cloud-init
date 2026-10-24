# This file is part of cloud-init. See LICENSE file for license information.

import logging
import shutil
from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.sources.azure import certs


@pytest.fixture
def data_file_path():
    """Return a helper that resolves Azure test data file paths."""

    def _path(name):
        return Path("tests", "data", "azure", name)

    return _path


@pytest.fixture
def cert_data(data_file_path):
    """Load the test certificate data, skipping if unavailable."""
    cert_file = data_file_path("pubkey_extract_cert")
    if not cert_file.exists():
        pytest.skip("Test data file not found")
    return cert_file.read_text()


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

_X509_CERT = dedent("""\
    -----BEGIN CERTIFICATE-----
    MIIB+TCCAeOgAwIBAgIBATANBgkqhkiG9w0BAQUFADAWMRQwEgYDVQQDDAtSb290
    -----END CERTIFICATE-----
    """)

# Some Azure-generated keys contained a CRLF after every 64 characters and
# at the end (LP: #1910835).
_AZURE_KEY = _VALID_RSA_KEY + " generated-by-azure"
_AZURE_CRLF_KEY = (
    "\r\n".join(_AZURE_KEY[i : i + 64] for i in range(0, len(_AZURE_KEY), 64))
    + "\r\n"
)

_CRLF_WARNING = (
    "cloudinit.sources.azure.certs",
    logging.WARNING,
    "SSH key contains embedded CRLF sequence(s) which are being removed.",
)


class TestIsOpensshFormatted:
    """Test is_openssh_formatted() function."""

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param(_VALID_RSA_KEY, id="rsa-without-comment"),
            pytest.param(_VALID_ED25519_KEY, id="ed25519"),
            pytest.param(_VALID_ECDSA_KEY, id="ecdsa"),
            # The parser treats CRLF as whitespace, so it does not reject
            # embedded CRLF. normalize_ssh_public_key() removes it instead.
            pytest.param(
                "ssh-rsa AAAAB3NzaC1yc2EAAAA\r\nBBBB user@host",
                id="embedded-crlf-not-detected",
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
            pytest.param("ssh-rsa", id="missing-key-data"),
            pytest.param(
                "not-a-key-type AAAAB3NzaC1yc2EAAAADAQABAAABAQ",
                id="malformed-key-type",
            ),
        ],
    )
    def test_invalid(self, value):
        """Non-OpenSSH strings should return False."""
        assert certs.is_openssh_formatted(value) is False


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

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_invalid_certificate_content(self, m_subp):
        """Certificate with invalid content should return False."""
        m_subp.side_effect = subp.ProcessExecutionError(
            "unable to load certificate"
        )

        assert certs.is_x509_certificate(_INVALID_X509_CERT) is False
        m_subp.assert_called_once()

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_valid_certificate_integration(self, cert_data):
        """Integration test: Actually validate certificate with openssl."""
        assert certs.is_x509_certificate(cert_data) is True

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_certificate_with_extra_whitespace_integration(self, cert_data):
        """Integration test: Certificate with extra whitespace validates."""
        assert certs.is_x509_certificate("\n\n" + cert_data + "\n\n") is True

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_invalid_certificate_integration(self):
        """Integration test: Reject invalid certificate with real openssl."""
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

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_extracts_all_valid_certificates(self, m_is_x509):
        """Should extract and return all valid certificates."""
        cert1 = dedent("""\
            -----BEGIN CERTIFICATE-----
            CERT1DATA
            -----END CERTIFICATE-----
            """)
        cert2 = dedent("""\
            -----BEGIN CERTIFICATE-----
            CERT2DATA
            -----END CERTIFICATE-----
            """)
        bundle = cert1 + "\n" + cert2

        m_is_x509.return_value = True

        result = certs.extract_x509_certificates(bundle)

        assert result == [cert1.strip(), cert2.strip()]

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_skips_private_keys(self, m_is_x509):
        """Should skip private keys and extract certificate."""
        private_key = dedent("""\
            -----BEGIN PRIVATE KEY-----
            PRIVATEKEYDATA
            -----END PRIVATE KEY-----
            """)
        certificate = dedent("""\
            -----BEGIN CERTIFICATE-----
            CERTDATA
            -----END CERTIFICATE-----
            """)
        bundle = private_key + "\n" + certificate

        m_is_x509.return_value = True

        result = certs.extract_x509_certificates(bundle)

        assert result == [certificate.strip()]

    @mock.patch("cloudinit.sources.azure.certs.is_x509_certificate")
    def test_skips_invalid_certs(self, m_is_x509):
        """Should skip invalid cert and return only valid ones."""
        invalid_cert = dedent("""\
            -----BEGIN CERTIFICATE-----
            INVALID
            -----END CERTIFICATE-----
            """)
        valid_cert = dedent("""\
            -----BEGIN CERTIFICATE-----
            VALID
            -----END CERTIFICATE-----
            """)
        bundle = invalid_cert + "\n" + valid_cert

        m_is_x509.side_effect = [False, True]

        result = certs.extract_x509_certificates(bundle)

        assert result == [valid_cert.strip()]

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_extraction_from_mixed_bundle_integration(self, cert_data):
        """Integration test: Extract cert from bundle with private key."""
        private_key = dedent("""\
            -----BEGIN PRIVATE KEY-----
            MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDExample
            -----END PRIVATE KEY-----
            """)
        bundle = private_key + "\n" + cert_data

        result = certs.extract_x509_certificates(bundle)

        assert result == [cert_data.strip()]


class TestConvertX509ToOpenssh:
    """Test convert_x509_to_openssh() function."""

    @mock.patch("cloudinit.sources.azure.certs.subp.subp")
    def test_conversion_with_mocked_commands(self, m_subp):
        """Test basic conversion flow with mocked subp calls."""
        cert = dedent("""\
            -----BEGIN CERTIFICATE-----
            MIIB+TCCAeOgAwIBAgIBATANBgkqhkiG9w0BAQUFADAWMRQwEgYDVQQDDAtSb290
            -----END CERTIFICATE-----
            """)
        pubkey = (
            "-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----"
        )
        expected_ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ..."

        m_subp.side_effect = [
            (pubkey, ""),
            (expected_ssh_key, ""),
        ]

        result = certs.convert_x509_to_openssh(cert)

        assert result == expected_ssh_key
        assert m_subp.call_count == 2

        openssl_call = m_subp.call_args_list[0]
        assert openssl_call[0][0] == ["openssl", "x509", "-noout", "-pubkey"]
        assert openssl_call[1]["data"] == cert

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
    def test_conversion_integration(self, cert_data, data_file_path):
        """Integration test: Convert certificate with real commands."""
        key_file = data_file_path("pubkey_extract_ssh_key")

        if not key_file.exists():
            pytest.skip("Test data files not found")

        expected_key = key_file.read_text().strip()

        result = certs.convert_x509_to_openssh(cert_data)
        assert result.strip() == expected_key


class TestNormalizeSshPublicKey:
    """Test normalize_ssh_public_key() function."""

    @pytest.mark.parametrize(
        "key, expected, warns",
        [
            pytest.param(
                _VALID_RSA_KEY, _VALID_RSA_KEY, False, id="unchanged"
            ),
            pytest.param(
                f"  {_VALID_RSA_KEY}\n",
                _VALID_RSA_KEY,
                False,
                id="surrounding-whitespace-stripped",
            ),
            pytest.param(
                f"{_VALID_RSA_KEY}\r\n",
                _VALID_RSA_KEY,
                False,
                id="trailing-crlf-stripped-without-warning",
            ),
            pytest.param(
                _AZURE_CRLF_KEY,
                _AZURE_KEY,
                True,
                id="embedded-crlf-removed-with-warning",
            ),
        ],
    )
    def test_openssh_key(self, key, expected, warns, caplog):
        """OpenSSH keys are trimmed and any embedded CRLF is removed.

        Only embedded CRLF logs a warning.
        """
        assert certs.normalize_ssh_public_key(key) == expected
        assert (_CRLF_WARNING in caplog.record_tuples) is warns

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("", id="empty"),
            pytest.param("not-a-supported-key", id="unsupported"),
            pytest.param("ssh-rsa", id="missing-key-data"),
        ],
    )
    def test_unsupported_key_raises_value_error(self, key):
        """A key that is neither OpenSSH nor x509 raises a ValueError."""
        with pytest.raises(ValueError, match="not in a supported format"):
            certs.normalize_ssh_public_key(key)

    @pytest.mark.parametrize(
        "cert",
        [
            pytest.param(_X509_CERT, id="lf"),
            pytest.param(_X509_CERT.replace("\n", "\r\n"), id="crlf"),
            pytest.param(
                "\r\n" + _X509_CERT.replace("\n", "\r\n") + "  ",
                id="crlf-with-surrounding-whitespace",
            ),
        ],
    )
    @mock.patch("cloudinit.sources.azure.certs.convert_x509_to_openssh")
    def test_x509_certificate_is_converted_unmodified(
        self, m_convert, cert, caplog
    ):
        """The certificate is passed to the conversion exactly as received."""
        caplog.set_level(logging.DEBUG)
        m_convert.return_value = "ssh-rsa converted-from-x509\n"

        result = certs.normalize_ssh_public_key(cert)

        assert result == "ssh-rsa converted-from-x509"
        m_convert.assert_called_once_with(cert)
        assert "CRLF" not in caplog.text

    @pytest.mark.skipif(
        shutil.which("openssl") is None, reason="openssl not available"
    )
    @pytest.mark.allow_subp_for("openssl")
    def test_x509_conversion_failure_raises_value_error(self):
        """Malformed PEM fails real conversion and raises a ValueError."""
        with pytest.raises(
            ValueError, match="Failed to convert x509 certificate"
        ) as exc_info:
            certs.normalize_ssh_public_key(_INVALID_X509_CERT)

        assert isinstance(exc_info.value.__cause__, subp.ProcessExecutionError)

    @pytest.mark.skipif(
        shutil.which("openssl") is None or shutil.which("ssh-keygen") is None,
        reason="openssl or ssh-keygen not available",
    )
    @pytest.mark.allow_subp_for("openssl", "ssh-keygen")
    @pytest.mark.parametrize("line_ending", ["\n", "\r\n"], ids=["lf", "crlf"])
    def test_x509_certificate_integration(
        self, cert_data, data_file_path, line_ending, caplog
    ):
        """Integration test: LF and CRLF certificates are converted."""
        key_file = data_file_path("pubkey_extract_ssh_key")
        if not key_file.exists():
            pytest.skip("Test data files not found")
        caplog.set_level(logging.DEBUG)
        cert = cert_data.replace("\n", line_ending)

        result = certs.normalize_ssh_public_key(cert)

        assert result == key_file.read_text().strip()
        assert "CRLF" not in caplog.text
