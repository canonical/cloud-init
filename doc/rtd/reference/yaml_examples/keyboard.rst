.. _cce-keyboard:

Set keyboard layout
*******************

For a full list of keys, refer to the `keyboard module`_ schema.

Minimal example
===============

.. code-block:: yaml

    #cloud-config
    keyboard:
      layout: us

Additional options
==================

Set the specific keyboard layout, model, variant, and options.

.. code-block:: yaml

    #cloud-config
    keyboard:
      layout: de
      model: pc105
      variant: nodeadkeys
      options: compose:rwin

Alpine Linux setup
==================

For Alpine Linux, set specific keyboard layout and variant as used by
``setup-keymap``. Model and options are ignored.

.. code-block:: yaml

    #cloud-config
    keyboard:
      layout: gb
      variant: gb-extd


.. LINKS
.. _keyboard module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#keyboard
