.. _cce-keyboard:

Set keyboard layout
*******************

For a full list of keys, refer to the :ref:`keyboard module <mod_cc_keyboard>`
schema.

Minimal example
===============

Set the keyboard layout to "US"

.. literalinclude:: ../../../module-docs/cc_keyboard/example1.yaml
   :language: yaml
   :linenos:

Additional options
==================

Set the specific keyboard layout, model, variant, and options.

.. literalinclude:: ../../../module-docs/cc_keyboard/example2.yaml
   :language: yaml
   :linenos:

Alpine Linux setup
==================

For Alpine Linux, set specific keyboard layout and variant as used by
``setup-keymap``. Model and options are ignored.

.. literalinclude:: ../../../module-docs/cc_keyboard/example3.yaml
   :language: yaml
   :linenos:

