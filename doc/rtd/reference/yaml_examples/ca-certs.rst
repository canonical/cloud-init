.. _cce-ca-certs:

Add and configure trusted CA certificates
*****************************************

These examples demonstrate adding CA certificates to the system's CA store,
and configuring the same.

For a full list of keys, refer to the `CA certificates module`_ schema.

Add a single-line certificate
=============================

.. code-block:: yaml

    #cloud-config
    ca_certs:
      remove_defaults: true
      trusted:
        - single_line_cert
        - |
          -----BEGIN CERTIFICATE-----
          YOUR-ORGS-TRUSTED-CA-CERT-HERE
          -----END CERTIFICATE-----

Configure multiline certificates
================================

This example configures CA certificates (system-wide) to establish SSL/TLS
trust when the instance boots for the first time.

- If present and set to ``true``, the ``remove_defaults`` parameter will
  disable all trusted CA certifications normally shipped with Alpine, Debian or
  Ubuntu. On RedHat, this action will delete those certificates.

  This is primarily for security-sensitive use cases -- most users will not
  need this functionality.

- If present, the ``trusted`` parameter should contain a certificate (or list
  of certificates) to add to the system as trusted CA certificates.

  In this example, note the YAML multiline list syntax, which configures a list
  of multiline certificates.

.. code-block:: yaml

    #cloud-config
    ca_certs:
      remove_defaults: true

      trusted:
      - |
       -----BEGIN CERTIFICATE-----
       YOUR-ORGS-TRUSTED-CA-CERT-HERE
       -----END CERTIFICATE-----
      - |
       -----BEGIN CERTIFICATE-----
       YOUR-ORGS-TRUSTED-CA-CERT-HERE
       -----END CERTIFICATE-----

.. LINKS
.. _CA certificates module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ca-certificates
