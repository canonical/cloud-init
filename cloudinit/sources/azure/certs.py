# Copyright (C) 2024 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import re
from typing import List, Optional

from cloudinit import ssh_util, subp

LOG = logging.getLogger(__name__)

_CERTIFICATE_BLOCK_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


def is_openssh_formatted(key: str) -> bool:
    """Validate whether or not the key is OpenSSH-formatted.

    This checks if a given string is a valid OpenSSH public key format
    (e.g., ssh-rsa, ssh-ed25519, ecdsa-sha2-nistp256).

    """
    if not key:
        LOG.debug("Empty SSH key content provided.")
        return False

    parser = ssh_util.AuthKeyLineParser()
    akl = parser.parse(key)
    if akl.keytype is None:
        LOG.debug("SSH key type is missing.")
        return False

    return True


def is_x509_certificate(cert: str) -> bool:
    """Check if the input string is an x509 certificate in PEM format.

    This validates that the certificate is a valid x509 certificate by
    attempting to parse it with openssl.
    """
    if not cert:
        LOG.debug("Empty certificate provided.")
        return False

    cert = cert.strip()

    if "-----BEGIN CERTIFICATE-----" not in cert:
        LOG.debug("No BEGIN CERTIFICATE marker.")
        return False

    if "-----END CERTIFICATE-----" not in cert:
        LOG.debug("No END CERTIFICATE marker.")
        return False

    # Attempt to parse the certificate with openssl to validate it.
    try:
        cmd = ["openssl", "x509", "-noout", "-text"]
        subp.subp(cmd, data=cert)
        return True
    except subp.ProcessExecutionError as e:
        LOG.debug("Certificate could not be parsed: %s", e)
        return False


def extract_x509_certificates(data: Optional[str]) -> List[str]:
    """Extract and validate all x509 certificates from a data bundle.

    The data may contain a mix of certificates and private keys. This function
    finds all valid x509 certificates and returns them.

    Args:
        data: String containing certificate data, potentially mixed with
              private keys or other content. May be None.

    Returns:
        A list of valid x509 certificate strings. Empty if none are found.
    """
    if not data:
        LOG.debug("No data provided for certificate extraction.")
        return []

    certificates = []
    for match in _CERTIFICATE_BLOCK_RE.finditer(data):
        certificate = match.group(0)
        if is_x509_certificate(certificate):
            LOG.debug("Successfully extracted x509 certificate from bundle.")
            certificates.append(certificate)
        else:
            LOG.debug(
                "Found certificate block but validation failed, skipping."
            )

    if not certificates:
        LOG.debug("No valid x509 certificates found in data bundle.")

    return certificates


def convert_x509_to_openssh(certificate: str) -> str:
    """Convert an x509 certificate to OpenSSH public key format."""
    LOG.debug("Converting x509 certificate to OpenSSH public key format.")
    openssl_cmd = ["openssl", "x509", "-noout", "-pubkey"]
    try:
        pub_key, _ = subp.subp(openssl_cmd, data=certificate)
    except subp.ProcessExecutionError as e:
        LOG.warning("Failed to extract public key from certificate: %s", e)
        raise

    keygen_cmd = ["ssh-keygen", "-i", "-m", "PKCS8", "-f", "/dev/stdin"]
    try:
        ssh_key, _ = subp.subp(keygen_cmd, data=pub_key)
    except subp.ProcessExecutionError as e:
        LOG.warning("Failed to convert public key to OpenSSH format: %s", e)
        raise

    LOG.debug("Successfully converted x509 certificate to OpenSSH format.")
    return ssh_key


def normalize_ssh_public_key(key: str) -> str:
    """Normalize an IMDS-provided public key into OpenSSH format.

    Keys provided by IMDS may already be in OpenSSH format or may be x509
    certificates:

    - x509 certificates are converted to OpenSSH format. The certificate is
      passed to the conversion unmodified, since PEM is multi-line and CRLF
      line endings are valid.
    - OpenSSH keys must be single-line, so surrounding whitespace is stripped
      and embedded CRLF is removed with a warning. Some Azure-generated keys
      included CRLF every 64 characters and needed this cleanup for use in
      authorized_keys. The x509 fallback worked because conversion removed
      the line breaks. See:
      https://bugs.launchpad.net/cloud-init/+bug/1910835
      This is no longer expected, but the CRLF is still removed so that any
      such key keeps working instead of breaking authorized_keys.

    :param key: The public key data as provided by IMDS.

    :raises ValueError: if the key is not a valid OpenSSH key, or is an
        x509 certificate that cannot be converted.

    :returns: The public key in OpenSSH format.
    """
    if "-----BEGIN CERTIFICATE-----" in key:
        try:
            return convert_x509_to_openssh(key).strip()
        except subp.ProcessExecutionError as error:
            raise ValueError(
                "Failed to convert x509 certificate to OpenSSH format"
            ) from error

    key = key.strip()
    if "\r\n" in key:
        LOG.warning(
            "SSH key contains embedded CRLF sequence(s) which are being "
            "removed."
        )
        key = key.replace("\r\n", "")

    if not is_openssh_formatted(key):
        raise ValueError("Key is not in a supported format")

    return key
