.. _cce-update-etc-hosts:

Update the hosts file
*********************

For a full list of keys, refer to the
:ref:`update etc hosts module <mod_cc_update_etc_hosts>` schema.

Do not update /etc/hosts
========================

The default behavior is for cloud-init to not update or manage ``/etc/hosts``
at all. Whatever is present at instance boot time will be present after boot.
User changes will not be overwritten.

.. literalinclude:: ../../../module-docs/cc_update_etc_hosts/example1.yaml
   :language: yaml
   :linenos:

Manage /etc/hosts with cloud-init
=================================

With this example, ``/etc/hosts`` will be re-written on every boot from
``/etc/cloud/templates/hosts.tmpl``.

The strings ``$hostname`` and ``$fqdn`` are replaced in the template with the
appropriate values -- either from the ``config-config`` ``fqdn``, or
``hostname`` if provided.

When absent, the meta-data will be checked for ``local-hostname`` which
can be split into ``<hostname>.<fqdn>``.

To make your modifications persist across a reboot, you must modify
``/etc/cloud/templates/hosts.tmpl``.

.. literalinclude:: ../../../module-docs/cc_update_etc_hosts/example2.yaml
   :language: yaml
   :linenos:

Update /etc/hosts every boot
============================

Updating ``/etc/hosts`` every boot, providing a ``localhost`` 127.0.1.1 entry
with the latest hostname and FQDN (as provided by either IMDS or cloud-config).

All other entries will be left unmodified.

``ping hostname`` will ping ``127.0.1.1``.

.. literalinclude:: ../../../module-docs/cc_update_etc_hosts/example3.yaml
   :language: yaml
   :linenos:

