.. _cce-resolv-conf:

Configure resolv.conf
*********************

When it comes to managing nameserver information on your operating system, many
distros have moved away from manually editing the ``/etc/resolv.conf`` file.

It's often recommended to use :ref:`network configuration <network_config>`
instead. Be sure to verify the preferred method for your distro before making
any edits to the ``resolv.conf`` file.

For a full list of keys, refer to the `resolv conf module`_ schema.

.. code-block:: yaml

    #cloud-config
    manage_resolv_conf: true
    resolv_conf:
      nameservers:
        - 8.8.8.8
        - 8.8.4.4
      searchdomains:
        - foo.example.com
        - bar.example.com
      domain: example.com
      sortlist:
        - 10.0.0.1/255
        - 10.0.0.2
      options:
        rotate: true
        timeout: 1

.. LINKS
.. _resolv conf module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#resolv-conf
