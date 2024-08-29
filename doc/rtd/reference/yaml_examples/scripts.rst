.. _cce-scripts:

Run scripts
***********

Scripts can be run by cloud-init by ensuring that the scripts are placed in
the correct directory on the datasource.

Run per-boot scripts
====================

Scripts in the ``scripts/per-boot`` directory are run on
every boot, and in alphabetical order. This module takes no config keys.

For more information, refer to the
:ref:`scripts per boot module <mod_cc_scripts_per_boot>` docs.

Run per-instance scripts
========================

Scripts in the ``scripts/per-instance`` directory are run
when a new instance is first booted, and in alphabetical order. This module
takes no config keys.

For more information, refer to the
:ref:`scripts per instance module <mod_cc_scripts_per_instance>` docs.

Run one-time scripts
====================

Scripts in the ``scripts/per-once`` directory are run only
once, and in alphabetical order. Changes to the instance will not force them
to be re-run.

For more information, refer to the
:ref:`scripts per once module <mod_cc_scripts_per_once>` docs.

Run all user scripts
====================

This module runs all user scripts present in the ``scripts`` directory. Any
cloud config parts with a ``#!`` will be treated as a script, and run in the
order they are specified in the configuration. This module takes no config
keys.

For more information, refer to the
:ref:`scripts user module <mod_cc_scripts_user>` docs.

Run vendor scripts
==================

Scripts in the ``scripts/vendor`` directory are run when a new instance is
first booted, and in alphabetical order.

For a full list of keys, refer to the
:ref:`scripts vendor module <mod_cc_scripts_vendor>` docs.

Example 1
---------

.. literalinclude:: ../../../module-docs/cc_scripts_vendor/example1.yaml
   :language: yaml
   :linenos:

Example 2
---------

.. literalinclude:: ../../../module-docs/cc_scripts_vendor/example2.yaml
   :language: yaml
   :linenos:

Example 3
---------

With this example, vendor data will not be processed.

.. literalinclude:: ../../../module-docs/cc_scripts_vendor/example3.yaml
   :language: yaml
   :linenos:

