.. _cce-set-hostname:

Set hostname and FQDN
*********************

For a full list of keys, refer to the
:ref:`set hostname module <mod_cc_set_hostname>` schema.

Example 1
=========

.. literalinclude:: ../../../module-docs/cc_set_hostname/example1.yaml
   :language: yaml
   :linenos:

Example 2
=========

.. literalinclude:: ../../../module-docs/cc_set_hostname/example2.yaml
   :language: yaml
   :linenos:

Example 3
=========

On a machine without an ``/etc/hostname`` file, don't create it.

In most clouds, this will result in a DHCP-configured hostname provided by the
cloud.

.. literalinclude:: ../../../module-docs/cc_set_hostname/example3.yaml
   :language: yaml
   :linenos:

