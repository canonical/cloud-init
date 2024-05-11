.. _cce-ubuntu-drivers:

Third party drivers in Ubuntu
******************************

This example demonstrates how to install third-party driver packages in
Ubuntu.

For a full list of keys, refer to the `Ubuntu drivers module`_ schema.

.. code-block:: yaml

    #cloud-config
    drivers:
      nvidia:
        license-accepted: true


.. LINKS
.. _Ubuntu drivers module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ubuntu-drivers
