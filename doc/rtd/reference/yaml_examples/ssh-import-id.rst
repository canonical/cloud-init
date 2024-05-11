.. _cce-SSH import ID:

Import SSH ID
*************

This example imports SSH keys from:

- GitHub (``gh:``)
- A public keyserver (in this case, Launchpad, ``lp:``)

Keys are referenced by the username they are associated with on the keyserver.

For a full list of keys, refer to the `SSH import ID module`_ schema.

.. code-block:: yaml

    #cloud-config
    ssh_import_id:
     - username
     - gh:username
     - lp:username

.. LINKS
.. _SSH import ID module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#SSH import ID
