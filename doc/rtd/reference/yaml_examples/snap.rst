.. _cce-snap:

Manage snaps
************

These examples will show you how to set up ``snapd`` and install snap packages.

For a full list of keys, refer to the `snap module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    snap:
        assertions:
          00: |
            signed_assertion_blob_here
          02: |
            signed_assertion_blob_here
        commands:
          00: snap create-user --sudoer --known <snap-user>@mydomain.com
          01: snap install canonical-livepatch
          02: canonical-livepatch enable <AUTH_TOKEN>

Example 2
=========

For convenience, the ``snap`` command can be omitted when specifying commands
as a list, and ``'snap'`` will automatically be prepended. The following
commands are all equivalent:

.. code-block:: yaml

    #cloud-config
    snap:
      commands:
        - ['install', 'vlc']
        - ['snap', 'install', 'vlc']
        - snap install vlc
        - 'snap install vlc'

In addition to using a list of commands, as in this example...

Example 3
=========

\...you can also use a list of assertions.

.. code-block:: yaml

    #cloud-config
    snap:
      assertions:
        - signed_assertion_blob_here
        - |
          signed_assertion_blob_here

.. LINKS
.. _snap module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#snap
