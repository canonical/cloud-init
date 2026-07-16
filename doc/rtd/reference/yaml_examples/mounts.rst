.. _cce-mounts:

Configure mount points and swap files
*************************************

For a full list of keys, refer to the :ref:`mounts module <mod_cc_mounts>`
schema.

Create swap file
================

This example creates a 2 GB swap file at ``/swapfile`` using human-readable
values.

.. literalinclude:: ../../../module-docs/cc_mounts/example2.yaml
   :language: yaml
   :linenos:

Set mount point and create swap file
====================================

In this example we mount:
- ``ephemeral0`` with the ``"noexec"`` flag,
- ``/dev/sdc`` with ``mount_default_fields``, and
- ``/dev/xvdh`` with ``custom fs_passno`` "0" to avoid ``fsck`` on the mount.

The config also provides an automatically-sized swap with a maximum size of
10485760 bytes.

.. literalinclude:: ../../../module-docs/cc_mounts/example1.yaml
   :language: yaml
   :linenos:

Explanation of fields
=====================

Let us break down some of the options available.

Mounts
------

Set up mount points. ``mounts`` contains a list of lists. The inner list
contains entries for an ``/etc/fstab`` line, e.g.:

.. code-block:: yaml

   [ fs_spec, fs_file, fs_vfstype, fs_mntops, fs_freq, fs_passno ]

With defaults:

.. code-block:: yaml

   mounts:
     - [ ephemeral0, /mnt ]
     - [ swap, none, swap, sw, 0, 0 ]

To remove a previously-listed mount (i.e., a default one), list only the
``fs_spec``.  For example, to override the default, of mounting swap
``[ swap ]`` or ``[ swap, null ]``.

- If a device does not exist at the time, an entry will still be written to
  ``/etc/fstab``.
- ``/dev`` can be omitted for device names that begin with: ``xvd``, ``sd``,
  ``hd``, or ``vd``.
- If an entry does not have all 6 fields, they will be filled in with values
  from the ``mount_default_fields`` below.

.. note::
    You should set ``nofail`` (see ``man fstab``) for volumes that may not
    be attached at instance boot (or reboot).

Example for ``mounts``
----------------------

.. code-block:: yaml

    mounts:
     - [ ephemeral0, /mnt, auto, "defaults,noexec" ]
     - [ sdc, /opt/data ]
     - [ xvdh, /opt/data, "auto", "defaults,nofail", "0", "0" ]
     - [ dd, /dev/zero ]

Mount default fields
--------------------

The ``mount_default_fields`` values are used to fill in any incomplete entries
in ``mounts``. This must be an array, and must have 6 fields.

.. code-block:: yaml

    mount_default_fields: [ None, None, "auto", "defaults,nofail", "0", "2" ]

Swap
----

``swap`` can also be set up by the ``mounts`` module. The default behavior is
to not create any swap files, because ``size`` is set to 0.

.. code-block:: yaml

    swap:
      filename: /swap.img
      size: "auto" # or size in bytes
      maxsize: 10485760   # size in bytes

.. LINKS
.. _mounts module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#mounts
