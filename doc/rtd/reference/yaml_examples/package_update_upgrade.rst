.. _cce-update-upgrade:

Update, upgrade and install packages
************************************

These examples show you how to install, update, and upgrade packages during
boot.

For a full list of keys, refer to the
:ref:`package update upgrade install <mod_cc_package_update_upgrade_install>`
module schema.

Install arbitrary packages
==========================

.. code-block:: yaml

    #cloud-config
    packages:
     - pwgen
     - pastebinit
     - [libpython2.7, 2.7.3-0ubuntu3.1]

Update and upgrade packages
===========================

.. literalinclude:: ../../../module-docs/cc_package_update_upgrade_install/example1.yaml
   :language: yaml
   :linenos:

