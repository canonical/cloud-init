.. _cce-ssh:

Configure SSH and SSH keys
**************************

For a full list of keys, refer to the :ref:`SSH module <mod_cc_ssh>` schema.

General example
===============

.. literalinclude:: ../../../module-docs/cc_ssh/example1.yaml
   :language: yaml
   :linenos:

Configure instance's SSH keys
=============================

.. code-block:: yaml

    #cloud-config
    ssh_authorized_keys:
      - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEyQwBI6Z+nCSU... mykey@host
      - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEVUf2l5gSn5uR... smoser@brickies
    ssh_keys:
      rsa_private: |
        -----BEGIN RSA PRIVATE KEY-----
        MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+0Qcon2LZS/x...
        -----END RSA PRIVATE KEY-----
      rsa_public: ssh-rsa AAAAB3NzaC1AAAABIwAAAGEAoPRh... smoser@localhost
    no_ssh_fingerprints: false
    ssh:
      emit_keys_to_console: false

.. _cce-SSH-import-ID:

Import SSH ID
=============

This example imports SSH keys from:

- GitHub (``gh:``)
- A public keyserver (in this case, Launchpad, ``lp:``)

Keys are referenced by the username they are associated with on the keyserver.

For a full list of keys, refer to the
:ref:`SSH import ID module <mod_cc_ssh_import_id>` schema. You may also find it
helpful to consult `the manual page`_.

.. literalinclude:: ../../../module-docs/cc_ssh_import_id/example1.yaml
   :language: yaml
   :linenos:

.. _cce-ssh-authkey-fingerprints:

Log fingerprints of user SSH keys
=================================

Writing the fingerprints of authorized user keys to logs is enabled by default.

For a full list of keys, refer to the
:ref:`SSH authkey fingerprints module <mod_cc_ssh_authkey_fingerprints>`
schema.

Do not write SSH fingerprints
-----------------------------

This example prevents SSH fingerprints from being written. The default is
``false``.

.. literalinclude:: ../../../module-docs/cc_ssh_authkey_fingerprints/example1.yaml
   :language: yaml
   :linenos:

Configure hash type
-------------------

This example configures the hash type to be ``sha512`` instead of the default
``sha256``.

.. literalinclude:: ../../../module-docs/cc_ssh_authkey_fingerprints/example2.yaml
   :language: yaml
   :linenos:

.. _cce-keys-to-console:

Control SSH key printing to console
===================================

By default, all supported host keys (and their fingerprints) are written to
the console, but for security reasons, this may not be desirable.

These examples show you how to prevent SSH host keys from being written out.
For a full list of keys, refer to the
:ref:`keys to console module <mod_cc_keys_to_console>` schema.

Do not print any SSH keys
-------------------------

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example1.yaml
   :language: yaml
   :linenos:

Do not print specific key types
-------------------------------

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example2.yaml
   :language: yaml
   :linenos:

Do not print specific fingerprints
----------------------------------

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example3.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _the manual page: https://manpages.ubuntu.com/manpages/noble/en/man1/ssh-import-id.1.html
