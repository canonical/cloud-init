.. _cce-set-hostname:

Set hostname and FQDN
*********************

For a full list of keys, refer to the `set hostname module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    preserve_hostname: true

Example 2
=========

.. code-block:: yaml

    #cloud-config
    hostname: myhost
    create_hostname_file: true
    fqdn: myhost.example.com
    prefer_fqdn_over_hostname: true

Example 3
=========

Don't create the ``/etc/hostname`` file (on a machine that doesn't have one).

In most clouds, this will result in a DHCP-configured hostname provided by the
cloud.

.. code-block:: yaml

    #cloud-config
    create_hostname_file: false

.. LINKS
.. _set hostname module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#set-hostname
