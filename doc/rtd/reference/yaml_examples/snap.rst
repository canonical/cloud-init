.. _cce-snap:

Manage snaps
************

These examples will show you how to set up ``snapd`` and install snap packages.

For a full list of keys, refer to the :ref:`snap module <mod_cc_snap>` schema.

General usage
=============

.. literalinclude:: ../../../module-docs/cc_snap/example1.yaml
   :language: yaml
   :linenos:

Omitting the snap command
=========================

For convenience, the ``snap`` command can be omitted when specifying commands
as a list, and ``'snap'`` will automatically be prepended. The following
commands are all equivalent:

.. literalinclude:: ../../../module-docs/cc_snap/example2.yaml
   :language: yaml
   :linenos:

Using lists
===========

You can use a list of commands:

.. literalinclude:: ../../../module-docs/cc_snap/example3.yaml
   :language: yaml
   :linenos:

And you can also use a list of assertions:

.. literalinclude:: ../../../module-docs/cc_snap/example4.yaml
   :language: yaml
   :linenos:

