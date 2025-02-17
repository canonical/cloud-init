.. _launching:

Launch a local instance with cloud-init
***************************************

It’s very likely that you will want to test your cloud-init configuration
locally before deploying it to the cloud.

Fortunately, there are several different virtual machine (VM) and container
tools ideal for this sort of local testing.

Due to differences across platforms, initializing and launching instances with
cloud-init can vary. Here we present instructions for various platforms, or
links to instructions where platforms have provided their preferred methods for
using cloud-init.

* :ref:`Launch with QEMU <launch_qemu>`
* :ref:`Launch with LXD <launch_lxd>`
* :ref:`Launch with Multipass <launch_multipass>`
* :ref:`Launch with libvirt <launch_libvirt>`
* :ref:`Launch with WSL <launch_wsl>`

.. toctree::
   :maxdepth: 2
   :hidden:

   QEMU <launch_qemu.rst>
   LXD <launch_lxd.rst>
   Multipass <launch_multipass.rst>
   Libvirt <launch_libvirt.rst>
   WSL <launch_wsl.rst>
