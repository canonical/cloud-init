.. _cce-boot-cmds:

Run commands during boot
************************

Both ``runcmd`` and ``bootcmd`` can be used to run commands during the boot
process.

- ``bootcmd`` runs on every boot, and is typically used to run commands very
  early in the boot process (just after a boothook, and often before other
  cloud-init modules have run).
- ``runcmd`` only runs on first boot, **after** the instance has been started
  and all other configuration has been applied.

Run commands only on first boot
===============================

``runcmd`` contains either a list of lists or a list of strings. Each item is
run in order, with output printed to the console.

The list must be written in proper YAML -- be sure to quote any characters
such as colons (``:``) that would otherwise be "eaten".

For a full list of keys, refer to the :ref:`runcmd module <mod_cc_runcmd>`
schema.

.. literalinclude:: ../../../module-docs/cc_runcmd/example1.yaml
   :language: yaml
   :linenos:

.. note::
   Don't write files to ``/tmp`` from cloud-init -- use ``/run/somedir``
   instead. Early boot environments can race ``systemd-tmpfiles-clean`` (LP:
   #1707222).

Run commands in early boot
==========================

- The ``INSTANCE_ID`` variable will be set to the current instance ID by
  default.
- The ``cloud-init-per`` command can be used to make ``bootcmd`` run exactly
  once.

For a full list of keys, refer to the :ref:`bootcmd module <mod_cc_bootcmd>`
schema.

.. literalinclude:: ../../../module-docs/cc_bootcmd/example1.yaml
   :language: yaml
   :linenos:

