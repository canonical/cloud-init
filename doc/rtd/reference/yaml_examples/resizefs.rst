.. _cce-resizefs:

Resize filesystem
*****************

These examples show how to resize a filesystem to use all available space on
the partition. The ``resizefs`` module can be used alongside the ``growpart``
module so that if the root partition is resized by ``growpart`` then the root
filesystem is also resized.

For a full list of keys, refer to the :ref:`resizefs module <mod_cc_resizefs>`
and the :ref:`growpart module <mod_cc_growpart>` schema.

Disable root filesystem resize operation
========================================

.. literalinclude:: ../../../module-docs/cc_resizefs/example1.yaml
   :language: yaml
   :linenos:

Run resize operation in background
==================================

.. literalinclude:: ../../../module-docs/cc_resizefs/example2.yaml
   :language: yaml
   :linenos:

