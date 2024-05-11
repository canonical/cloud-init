.. _cce-wireguard:

Configure Wireguard tunnel
**************************

In this example, we show how to configure one (or more) Wireguard interfaces,
and also provide (optional) readiness probes.

Each interface you wish to create will be named after the ``name`` parameter,
and the config will be written to a file located under ``config_path``.

The ``content`` parameter should be set with a valid Wireguard configuration.

The readiness probes ensure Wireguard has connectivity before continuing the
cloud-init process. This could be useful if you need access to specific
services like an internal APT repository server (e.g., Landscape) to install or
update packages.

For a full list of keys, refer to the `Wireguard module`_ schema.

.. code-block:: yaml

    #cloud-config
    wireguard:
      interfaces:
        - name: wg0
          config_path: /etc/wireguard/wg0.conf
          content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedip1>, <allowedip2>, ...
        - name: wg1
          config_path: /etc/wireguard/wg1.conf
          content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedip1>
      readinessprobe:
        - 'systemctl restart service'
        - 'curl https://webhook.endpoint/example'
        - 'nc -zv some-service-fqdn 443'


.. LINKS
.. _Wireguard module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#wireguard
