# Copyright (C) 2024 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import ssh_util, subp

LOG = logging.getLogger(__name__)


def is_openssh_formatted(key: str) -> bool:
    """Validate whether or not the key is OpenSSH-formatted.

    This checks if a given string is a valid OpenSSH public key format
    (e.g., ssh-rsa, ssh-ed25519, ecdsa-sha2-nistp256).
    """
    if not key:
        LOG.debug("OpenSSH key validation failed: empty key content provided.")
        return False
    if "\r\n" in key.strip():
        LOG.debug(
            "OpenSSH key validation failed: carriage returns detected in key."
        )
        return False

    parser = ssh_util.AuthKeyLineParser()
    try:
        akl = parser.parse(key)
    except TypeError:
        LOG.debug("OpenSSH key validation failed: parser rejected key.")
        return False

    if akl.keytype is None:
        LOG.debug("OpenSSH key validation failed: key type missing.")
        return False

    return True


def is_x509_certificate(cert: str) -> bool:
    """Check if the input string is an x509 certificate in PEM format.

    This validates that the certificate is a valid x509 certificate by
    attempting to parse it with openssl.
    """
    if not cert:
        LOG.debug("Certificate validation failed: empty certificate provided.")
        return False

    cert = cert.strip()

    if "-----BEGIN CERTIFICATE-----" not in cert:
        LOG.debug(
            "Certificate validation failed: missing BEGIN CERTIFICATE marker."
        )
        return False

    if "-----END CERTIFICATE-----" not in cert:
        LOG.debug(
            "Certificate validation failed: missing END CERTIFICATE marker."
        )
        return False

    # Attempt to parse the certificate with openssl to validate it.
    try:
        cmd = ["openssl", "x509", "-noout", "-text"]
        subp.subp(cmd, data=cert)
        return True
    except subp.ProcessExecutionError as e:
        LOG.debug("Certificate validation failed: %s", e)
        return False


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
