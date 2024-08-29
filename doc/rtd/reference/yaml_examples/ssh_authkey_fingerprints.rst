.. _cce-ssh-authkey-fingerprints:

Log fingerprints of user SSH keys
*********************************

Writing the fingerprints of authorized user keys to logs is enabled by default.

For a full list of keys, refer to the
:ref:`SSH authkey fingerprints module <mod_cc_ssh_authkey_fingerprints>`
schema.

Do not write SSH fingerprints
=============================

This example prevents SSH fingerprints from being written. The default is
``false``.

.. literalinclude:: ../../../module-docs/cc_ssh_authkey_fingerprints/example1.yaml
   :language: yaml
   :linenos:

Configure hash type
===================

This example configures the hash type to be ``sha512`` instead of the default
``sha256``.

.. literalinclude:: ../../../module-docs/cc_ssh_authkey_fingerprints/example2.yaml
   :language: yaml
   :linenos:

