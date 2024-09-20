.. _cce-update-upgrade:

Update, upgrade and install packages
************************************

These examples show you how to install, update, and upgrade packages during
boot. By default, this is set to "none", but if any packages are specified
then ``package_update`` will be set to ``true``.

Packages can be supplied as either a single package name, or as a list with
the format ``[<package>, <version>]`` (which will install the specific package
version.

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

