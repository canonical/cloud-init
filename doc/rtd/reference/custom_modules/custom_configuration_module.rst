.. _custom_configuration_module:

Custom Configuration Module
***************************

Custom 3rd-party out-of-tree configuration modules can be added to cloud-init
by:

#. :ref:`Implement a config module<module_creation>` in a Python file with its
   name starting with ``cc_``.

#. Place the file where the rest of config modules are located.
   On Ubuntu this path is typically:
   `/usr/lib/python3/dist-packages/cloudinit/config/`.

#. Extend the :ref:`base-configuration's <base_config_module_keys>`
   ``cloud_init_modules``, ``cloud_config_modules`` or ``cloud_final_modules``
   to let the config module run on one of those stages.

.. warning ::
   The config jsonschema validation functionality is going to complain about
   unknown config keys introduced by custom modules and there is not an easy
   way for custom modules to define their keys schema-wise.
