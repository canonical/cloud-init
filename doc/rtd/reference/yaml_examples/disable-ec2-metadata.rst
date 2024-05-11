.. _cce-disable-ec2-metadata:

Disable AWS EC2 metadata
************************

The default value for this module is ``false``. Setting it to ``true`` disables
the IPv4 routes to EC2 metadata.

For more details, refer to the `disable EC2 metadata module`_ schema.

.. code-block:: yaml

    #cloud-config
    disable_ec2_metadata: true

.. LINKS
.. _disable EC2 metadata module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#disable-ec2-metadata
