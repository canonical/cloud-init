.. _cce-scripts:

Run scripts
***********

Scripts can be run by cloud-init by ensuring that the scripts are placed in
the correct directory on the datasource.

Run per-boot scripts
====================

Scripts in the ``scripts/per-boot`` directory are run on
every boot, and in alphabetical order. This module takes no config keys.

For more information, refer to the `scripts per boot module`_ docs.

Run per-instance scripts
========================

Scripts in the ``scripts/per-instance`` directory are run
when a new instance is first booted, and in alphabetical order. This module
takes no config keys.

For more information, refer to the `scripts per instance module`_ docs.

Run one-time scripts
====================

Scripts in the ``scripts/per-once`` directory are run only
once, and in alphabetical order. Changes to the instance will not force them
to be re-run.

For more information, refer to the `scripts per once module`_ docs.

Run all user scripts
====================

This module runs all user scripts present in the ``scripts`` directory. Any
cloud config parts with a ``#!`` will be treated as a script, and run in the
order they are specified in the configuration. This module takes no config
keys.

For more information, refer to the `scripts user module`_ docs.

Run vendor scripts
==================

Scripts in the ``scripts/vendor`` directory are run when a new instance is
first booted, and in alphabetical order.

For a full list of keys, refer to the `scripts vendor module`_ docs.

Example 1
---------

.. code-block:: yaml

    #cloud-config
    vendor_data:
      enabled: true
      prefix: /usr/bin/ltrace

Example 2
---------

.. code-block:: yaml

    #cloud-config
    vendor_data:
      enabled: true
      prefix: [timeout, 30]

Example 3
---------

With this example, vendor data will not be processed.

.. code-block:: yaml

    #cloud-config
    vendor_data:
      enabled: false

.. LINKS
.. _scripts per boot module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#scripts-per-boot
.. _scripts per instance module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#scripts-per-instance
.. _scripts per once module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#scripts-per-once
.. _scripts user module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#scripts-user
.. _scripts vendor module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#scripts-vendor
