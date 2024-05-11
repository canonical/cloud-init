.. _cce-byobu:

Enable/disable Byobu
********************

For a full list of keys, refer to the `Byobu module`_ schema.

Enable for the default user
===========================

.. code-block:: yaml

    #cloud-config
    byobu_by_default: enable-user

Disable system-wide
===================

.. code-block:: yaml

    #cloud-config
    byobu_by_default: disable-system

.. LINKS
.. _Byobu module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#byobu
