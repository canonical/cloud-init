.. _cce-resizefs:

Resize filesystem
*****************

These examples show how to resize a filesystem to use all available space on
the partition. The ``resizefs`` module can be used alongside the ``growpart``
module so that if the root partition is resized by ``growpart`` then the root
filesystem is also resized.

For a full list of keys, refer to the `resize filesystem module`_ and the
`growpart module`_ schema.

Disable root filesystem resize operation
========================================

.. code-block:: yaml

    #cloud-config
    resize_rootfs: false

Run resize operation in background
==================================

.. code-block:: yaml

    #cloud-config
    resize_rootfs: noblock

.. LINKS
.. _resize filesystem module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#byobu
.. _growpart module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#growpart
