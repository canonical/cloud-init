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
      - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEA3FSyQwBI6Z+nCSU... mykey@host
      - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uR... smoser@brickies
    ssh_keys:
      rsa_private: |
        -----BEGIN RSA PRIVATE KEY-----
        MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+00R7VVu2iV9Qcon2LZS/x

        ...

        -----END RSA PRIVATE KEY-----
      rsa_public: ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEAoPRh... smoser@localhost
    no_ssh_fingerprints: false
    ssh:
      emit_keys_to_console: false

* ``ssh_authorized_keys``:
  Adds each entry to ``~/.ssh/authorized_keys`` for the configured user (or the
  first user defined in the user definition directive).

* ``ssh_keys``:
  Sends pre-generated SSH private keys to the server. If these are present,
  they will be written to ``/etc/ssh`` and new random keys will not be
  generated. In addition to ``rsa`` as shown in the example, ``ecdsa`` is also
  supported.

* ``no_ssh_fingerprints``:
  By default, the fingerprints of the authorized keys for users cloud-init adds
  are printed to the console. Setting ``no_ssh_fingerprints`` to ``true``
  suppresses this output.

* ``emit_keys_to_console``:
  By default, (most) SSH host keys are printed to the console. Setting
  ``emit_keys_to_console: false`` suppresses this output.

