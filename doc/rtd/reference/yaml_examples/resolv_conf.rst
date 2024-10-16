.. _cce-resolv-conf:

Configure resolv.conf
*********************

When it comes to managing nameserver information on your operating system, many
distros have moved away from manually editing the ``/etc/resolv.conf`` file.

It's often recommended to use :ref:`network configuration <network_config>`
instead. Be sure to verify the preferred method for your distro before making
any edits to the ``resolv.conf`` file.

For a full list of keys, refer to the
:ref:`resolv conf module <mod_cc_resolv_conf>` schema.

.. literalinclude:: ../../../module-docs/cc_resolv_conf/example1.yaml
   :language: yaml
   :linenos:

