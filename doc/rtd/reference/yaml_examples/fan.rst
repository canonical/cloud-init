.. _cce-fan:

Configure Ubuntu fan networking
*******************************

This example will install the ``ubuntu-fan`` package (if it is not already
 installed), write the config path, and start (or restart) the service.

For a full list of keys, refer to the `fan module`_ schema.

.. code-block:: yaml

    #cloud-config
    fan:
      config: |
        # fan 240
        10.0.0.0/8 eth0/16 dhcp
        10.0.0.0/8 eth1/16 dhcp off
        # fan 241
        241.0.0.0/8 eth0/16 dhcp
      config_path: /etc/network/fan

.. _fan module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#fan
