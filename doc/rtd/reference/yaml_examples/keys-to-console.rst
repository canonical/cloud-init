.. _cce-keys-to-console:

Control SSH key printing to console
***********************************

By default, all supported host keys (and their fingerprints) are written to
the console, but for security reasons, this may not be desirable.

These examples show you how to prevent SSH host keys from being written out.
For a full list of keys, refer to the `keys to console module`_ schema.

Do not print any keys
=====================

.. code-block:: yaml

    #cloud-config
    ssh:
      emit_keys_to_console: false

Do not print SSH key (by type)
==============================

.. code-block:: yaml

    #cloud-config
    ssh_key_console_blacklist: [rsa]

Do not print specific fingerprints
==================================

.. code-block:: yaml

    #cloud-config
    ssh_fp_console_blacklist:
    - E25451E0221B5773DEBFF178ECDACB160995AA89
    - FE76292D55E8B28EE6DB2B34B2D8A784F8C0AAB0

.. LINKS
.. _keys to console module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#keys-to-console
