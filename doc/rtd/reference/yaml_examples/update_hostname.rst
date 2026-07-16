.. _cce-update-hostname:

Update hostname and FQDN
************************

For a full list of keys, refer to the
:ref:`update hostname module <mod_cc_update_hostname>` schema.

Default behavior
================

When ``preserve_hostname`` is not specified, cloud-init updates
``/etc/hostname`` per-boot based on the cloud-provided ``local-hostname``
setting. If you manually change ``/etc/hostname`` after boot, cloud-init will
no longer modify it.

This default cloud-init behavior is equivalent to this cloud-config:

.. literalinclude:: ../../../module-docs/cc_update_hostname/example1.yaml
   :language: yaml
   :linenos:

Note that the same cloud-config will also prevent cloud-init from updating the
system hostname.

Prevent updates to ``/etc/hostname``
====================================

This example will prevent cloud-init from updating the system hostname or
``/etc/hostname``.

.. literalinclude:: ../../../module-docs/cc_update_hostname/example2.yaml
   :language: yaml
   :linenos:

Set hostname
============

This example sets the hostname to ``external.fqdn.me`` instead of ``myhost``.

.. literalinclude:: ../../../module-docs/cc_update_hostname/example4.yaml
   :language: yaml
   :linenos:

Override meta-data
==================

Set the hostname to ``external`` instead of ``external.fqdn.me`` when
meta-data provides the ``local-hostname``: ``external.fqdn.me``.

.. literalinclude:: ../../../module-docs/cc_update_hostname/example5.yaml
   :language: yaml
   :linenos:

Don't create ``/etc/hostname`` file
===================================

On a machine without an ``/etc/hostname`` file, this config instructs
cloud-init not to create one.

In most clouds, this will result in a DHCP-configured hostname provided by the
cloud.

.. literalinclude:: ../../../module-docs/cc_update_hostname/example6.yaml
   :language: yaml
   :linenos:

