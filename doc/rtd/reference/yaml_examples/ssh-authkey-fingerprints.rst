.. _cce-ssh-authkey-fingerprints:

Log fingerprints of user SSH keys
*********************************

Writing the fingerprints of authorized user keys to logs is enable by default.

For a full list of keys, refer to the `SSH authkey fingerprints module`_
schema.

Do not write SSH fingerprints
=============================

This example prevents SSH fingerprints from being written. The default is
``false``.

.. code-block:: yaml

    #cloud-config
    no_ssh_fingerprints: true

Configure hash type
===================

This example configures the hash type to be ``sha512`` instead of the default
``sha256``.

.. code-block:: yaml

    #cloud-config
    authkey_hash: sha512


.. LINKS
.. _SSH authkey fingerprints module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ssh-authkey-fingerprints
