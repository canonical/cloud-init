.. _cce-update-hostname:

Update hostname and FQDN
************************

For a full list of keys, refer to the `update hostname module`_ schema.

Default behavior
================

When ``preserve_hostname`` is not specified, cloud-init updates
``/etc/hostname`` per-boot based on the cloud-provided ``local-hostname``
setting. If you manually change ``/etc/hostname`` after boot, cloud-init will
no longer modify it.

This default cloud-init behavior is equivalent to this cloud-config:

.. code-block:: yaml

    #cloud-config
    preserve_hostname: false

Note that the same cloud-config will also prevent cloud-init from updating the
system hostname.

Prevent updates to ``/etc/hostname``
====================================

This example will prevent cloud-init from updating ``/etc/hostname``.

.. code-block:: yaml

    #cloud-config
    preserve_hostname: true

Set hostname
============

This example sets the hostname to ``external.fqdn.me`` instead of ``myhost``.

.. code-block:: yaml

    #cloud-config
    fqdn: external.fqdn.me
    hostname: myhost
    prefer_fqdn_over_hostname: true
    create_hostname_file: true

Override cloud metadata
=======================

Set the hostname to ``external`` instead of ``external.fqdn.me`` when cloud
metadata provides the ``local-hostname``: ``external.fqdn.me``.

.. code-block:: yaml

    #cloud-config
    prefer_fqdn_over_hostname: false

Don't create ``/etc/hostname`` file
===================================

On a machine without an ``/etc/hostname`` file, this config instructs
cloud-init not to create one.

In most clouds, this will result in a DHCP-configured hostname provided by the
cloud.

.. code-block:: yaml

    #cloud-config
    create_hostname_file: false


.. LINKS
.. _update hostname module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#update-hostname
