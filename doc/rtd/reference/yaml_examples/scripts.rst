.. _cce-scripts:

Run vendor scripts
******************

Scripts can be run by cloud-init by ensuring that the scripts are placed in
the correct directory on the datasource.

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

