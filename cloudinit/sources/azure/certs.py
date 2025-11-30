# Copyright (C) 2024 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import re
from typing import Optional

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
        LOG.debug("Empty key content provided.")
        return False
    # See https://bugs.launchpad.net/cloud-init/+bug/1910835
    if "\r\n" in key.strip():
        LOG.debug("Key contains carriage returns.")
        return False

    parser = ssh_util.AuthKeyLineParser()
    try:
        akl = parser.parse(key)
    except TypeError:
        LOG.debug("Key could not be parsed.")
        return False

    if akl.keytype is None:
        LOG.debug("Key type is missing.")
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
        LOG.debug("Missing BEGIN CERTIFICATE marker.")
        return False

    if "-----END CERTIFICATE-----" not in cert:
        LOG.debug("Missing END CERTIFICATE marker.")
        return False

    # Attempt to parse the certificate with openssl to validate it.
    try:
        cmd = ["openssl", "x509", "-noout", "-text"]
        subp.subp(cmd, data=cert)
        return True
    except subp.ProcessExecutionError as e:
        LOG.debug("Certificate could not be parsed: %s", e)
        return False


def extract_x509_certificate(data: str) -> Optional[str]:
    """Extract and validate the first x509 certificate from a data bundle.

    The data may contain a mix of certificates and private keys. This function
    finds the first valid x509 certificate and returns it.

    Args:
        data: String containing certificate data, potentially mixed with
              private keys or other content.

    Returns:
        The first valid x509 certificate as a string, or None if no valid
        certificate is found.
    """
    if not data:
        LOG.debug("No data provided for certificate extraction.")
        return None

    for match in _CERTIFICATE_BLOCK_RE.finditer(data):
        certificate = match.group(0)
        if is_x509_certificate(certificate):
            LOG.debug("Successfully extracted x509 certificate from bundle.")
            return certificate
        LOG.debug("Found certificate block but validation failed, skipping.")

    LOG.debug("No valid x509 certificate found in data bundle.")
    return None


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
