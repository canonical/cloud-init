.. _cce-update-upgrade:

Update, upgrade and install packages
************************************

These examples show you how to install, update, and upgrade packages during
boot. By default, this is set to "none", but if any packages are specified
then ``package_update`` will be set to ``true``.

Packages can be supplied as either a single package name, or as a list with
the format ``[<package>, <version>]`` (which will install the specific package
version.

For a full list of keys, refer to the `package update upgrade install module`_
schema.

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

.. code-block:: yaml

    #cloud-config
    packages:
      - pwgen
      - pastebinit
      - [libpython3.8, 3.8.10-0ubuntu1~20.04.2]
      - snap:
        - certbot
        - [juju, --edge]
        - [lxd, --channel=5.15/stable]
      - apt:
        - mg
    package_update: true
    package_upgrade: true
    package_reboot_if_required: true

.. LINKS
.. _package update upgrade install module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#package-update-upgrade-install
