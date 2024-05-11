.. _cce-growpart:

Grow partitions
***************

For a full list of keys, refer to the `growpart module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    growpart:
      mode: auto
      devices: ["/"]
      ignore_growroot_disabled: false


Example 2
=========

.. code-block:: yaml

    #cloud-config
    growpart:
      mode: growpart
      devices:
        - "/"
        - "/dev/vdb1"
      ignore_growroot_disabled: true

.. LINKS
.. _growpart module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#growpart
