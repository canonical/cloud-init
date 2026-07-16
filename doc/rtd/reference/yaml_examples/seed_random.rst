.. _cce-seed-random:

Provide random seed data
************************

For a full list of keys, refer to the
:ref:`seed random module <mod_cc_seed_random>` schema.

Example 1
=========

.. literalinclude:: ../../../module-docs/cc_seed_random/example1.yaml
   :language: yaml
   :linenos:

Example 2
=========

This example uses ``pollinate`` to gather data from a remote entropy server,
and writes that data to ``/dev/urandom``:

.. literalinclude:: ../../../module-docs/cc_seed_random/example2.yaml
   :language: yaml
   :linenos:

