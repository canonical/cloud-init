.. _cce-install-hotplug:

Install hotplug udev rules
**************************

These examples show how to install the necessary udev rules to enable
hotplugging (if supported by the datasource).

For a full list of keys, refer to the `install hotplug module`_ schema.

Enable network device hotplugging
=================================

.. code-block:: yaml

    #cloud-config
    updates:
      network:
        when: ["hotplug"]

Enable alongside boot events
============================

.. code-block:: yaml

    #cloud-config
    updates:
      network:
        when: ["boot", "hotplug"]

.. LINKS
.. _install hotplug module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#install-hotplug
