.. _cce-install-hotplug:

Install hotplug udev rules
**************************

These examples show how to install the necessary udev rules to enable
hotplugging (if supported by the datasource).

For a full list of keys, refer to the
:ref:`install hotplug module <mod_cc_install_hotplug>` schema.

Enable network device hotplugging
=================================

.. literalinclude:: ../../../module-docs/cc_install_hotplug/example1.yaml
   :language: yaml
   :linenos:

Enable hotplug alongside boot events
====================================

.. literalinclude:: ../../../module-docs/cc_install_hotplug/example2.yaml
   :language: yaml
   :linenos:

