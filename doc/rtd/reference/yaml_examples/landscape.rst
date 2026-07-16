.. _cce-landscape:

Install Landscape client
************************

These examples will install and configure the Landscape client.

For a full list of keys, refer to the
:ref:`landscape module <mod_cc_landscape>` schema, or run
``man landscape-config``.

Example 1
=========

.. literalinclude:: ../../../module-docs/cc_landscape/example1.yaml
   :language: yaml
   :linenos:

Minimum viable config
=====================

The minimum viable Landscape config requires ``account_name`` and
``computer_title``.

.. literalinclude:: ../../../module-docs/cc_landscape/example2.yaml
   :language: yaml
   :linenos:

Install from a PPA
==================

To install ``landscape-client`` from a PPA, specify ``apt.sources``.

.. literalinclude:: ../../../module-docs/cc_landscape/example3.yaml
   :language: yaml
   :linenos:

