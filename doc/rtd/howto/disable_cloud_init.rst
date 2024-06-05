.. _disable-Cloud_init:

How to disable cloud-init
*************************

One may wish to disable cloud-init to ensure that it doesn't do anything on
subsequent boots. Some parts of cloud-init may run once per boot otherwise.

There are three cross-platform methods of disabling ``cloud-init``.

Method 1: text file
====================

To disable cloud-init, create the empty file
:file:`/etc/cloud/cloud-init.disabled`. During boot the operating system's init
system will check for the existence of this file. If it exists, cloud-init will
not be started.

Example:

.. code-block::

    $ touch /etc/cloud/cloud-init.disabled

Method 2: kernel command line
=============================

To disable cloud-init, add ``cloud-init=disabled`` to the kernel command line.

Example (using GRUB2 with Ubuntu):

.. code-block::

    $ echo 'GRUB_CMDLINE_LINUX="cloud-init=disabled"' >> /etc/default/grub
    $ grub-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg

Method 3: environment variable
==============================

To disable cloud-init, pass the environment variable
``KERNEL_CMDLINE=cloud-init=disabled`` into each of cloud-init's
processes.

Example (using systemd):

.. code-block::

    $ echo "DefaultEnvironment=KERNEL_CMDLINE=cloud-init=disabled" >> /etc/systemd/system.conf
