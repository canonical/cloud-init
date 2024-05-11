.. _cce-spacewalk:

Install and configure Spacewalk
*******************************

The example demonstrates the installation and basic configuration of
`Spacewalk`_.

For a full list of keys, refer to the `Spacewalk module`_ schema.

.. code-block:: yaml

    #cloud-config
    spacewalk:
      server: <url>
      proxy: <proxy host>
      activation_key: <key>

.. LINKS
.. _Spacewalk: https://fedorahosted.org/spacewalk/
.. _Spacewalk module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#spacewalk
