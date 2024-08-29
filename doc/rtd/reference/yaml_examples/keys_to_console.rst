.. _cce-keys-to-console:

Control SSH key printing to console
***********************************

By default, all supported host keys (and their fingerprints) are written to
the console, but for security reasons, this may not be desirable.

These examples show you how to prevent SSH host keys from being written out.
For a full list of keys, refer to the
:ref:`keys to console module <mod_cc_keys_to_console>` schema.

Do not print any SSH keys
=========================

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example1.yaml
   :language: yaml
   :linenos:

Do not print specific key types
===============================

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example2.yaml
   :language: yaml
   :linenos:

Do not print specific fingerprints
==================================

.. literalinclude:: ../../../module-docs/cc_keys_to_console/example3.yaml
   :language: yaml
   :linenos:

