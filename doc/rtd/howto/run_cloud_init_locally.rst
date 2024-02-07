.. _run_cloud_init_locally:

How to run ``cloud-init`` locally
*********************************

It's very likely that you will want to test ``cloud-init`` locally before
deploying it to the cloud. Fortunately, there are several different virtual
machine (VM) and container tools that are ideal for this sort of local
testing.

* :ref:`boot cloud-init with QEMU <run_with_qemu>`
* :ref:`boot cloud-init with LXD <run_with_lxd>`
* :ref:`boot cloud-init with Libvirt <run_with_libvirt>`
* :ref:`boot cloud-init with Multipass <run_with_multipass>`

.. _run_with_qemu:

QEMU
====

`QEMU`_ is a general purpose computer hardware emulator that is capable of
running virtual machines with hardware acceleration as well as emulating the
instruction sets of different architectures than the host that you are
running on.

The ``NoCloud`` datasource allows users to provide their own user data,
metadata, or network configuration directly to an instance without running a
network service. This is helpful for launching local cloud images with QEMU.

Create your configuration
-------------------------

We will leave the :file:`network-config` and :file:`meta-data` files empty, but
populate :file:`user-data` with a cloud-init configuration. You may edit the
:file:`network-config` and :file:`meta-data` files if you have a config to
provide.

.. code-block:: shell-session

    $ touch network-config
    $ touch meta-data
    $ cat >user-data <<EOF
    #cloud-config
    password: password
    chpasswd:
      expire: False
    ssh_pwauth: True
    EOF

Create an ISO disk
------------------

This disk is used to pass configuration to cloud-init. Create it with the
:command:`genisoimage` command:

.. code-block:: shell-session

    genisoimage \
        -output seed.img \
        -volid cidata -rational-rock -joliet \
        user-data meta-data network-config


Download a cloud image
----------------------

Download an Ubuntu image to run:

.. code-block:: shell-session

    wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img

Boot the image with the ISO attached
------------------------------------

Boot the cloud image with our configuration, :file:`seed.img`, to QEMU:

.. code-block:: shell-session

    $ qemu-system-x86_64 -m 1024 -net nic -net user \
        -hda jammy-server-cloudimg-amd64.img \
        -hdb seed.img

The now-booted image will allow for login using the password provided above.

For additional configuration, users can provide much more detailed
configuration in the empty :file:`network-config` and :file:`meta-data` files.

.. note::

    See the :ref:`network_config_v2` page for details on the format and config
    of network configuration. To learn more about the possible values for
    metadata, check out the :ref:`datasource_nocloud` page.

.. _run_with_lxd:

LXD
===

`LXD`_ offers a streamlined user experience for using Linux system containers.
With LXD, the following command initialises a container with user data:

.. code-block:: shell-session

    $ lxc init ubuntu-daily:jammy test-container
    $ lxc config set test-container user.user-data - < userdata.yaml
    $ lxc start test-container

To avoid the extra commands this can also be done at launch:

.. code-block:: shell-session

    $ lxc launch ubuntu-daily:jammy test-container --config=user.user-data="$(cat userdata.yaml)"

Finally, a profile can be set up with the specific data if you need to
launch this multiple times:

.. code-block:: shell-session

    $ lxc profile create dev-user-data
    $ lxc profile set dev-user-data user.user-data - < cloud-init-config.yaml
    $ lxc launch ubuntu-daily:jammy test-container -p default -p dev-user-data

LXD configuration types
-----------------------

The above examples all show how to pass user data. To pass other types of
configuration data use the configuration options specified below:

+----------------+---------------------------+
| Data           | Configuration option      |
+================+===========================+
| user data      | cloud-init.user-data      |
+----------------+---------------------------+
| vendor data    | cloud-init.vendor-data    |
+----------------+---------------------------+
| network config | cloud-init.network-config |
+----------------+---------------------------+

See the LXD `Instance Configuration`_ docs for more info about configuration
values or the LXD `Custom Network Configuration`_ document for more about
custom network config.

.. _run_with_libvirt:

Libvirt
=======

`Libvirt`_ is a tool for managing virtual machines and containers.

Create your configuration
-------------------------

We will leave the :file:`network-config` and :file:`meta-data` files empty, but
populate user-data with a cloud-init configuration. You may edit the
:file:`network-config` and :file:`meta-data` files if you have a config to
provide.

.. code-block:: shell-session

    $ touch network-config
    $ touch meta-data
    $ cat >user-data <<EOF
    #cloud-config
    password: password
    chpasswd:
      expire: False
    ssh_pwauth: True
    EOF

Download a cloud image
----------------------

Download an Ubuntu image to run:

.. code-block:: shell-session

    wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img


Create an instance
------------------

.. code-block:: shell-session

    virt-install --name cloud-init-001 --memory 4000 --noreboot \
        --os-variant detect=on,name=ubuntujammy \
        --disk=size=10,backing_store="$(pwd)/jammy-server-cloudimg-amd64.img" \
        --cloud-init user-data="$(pwd)/user-data,meta-data=$(pwd)/meta-data,network-config=$(pwd)/network-config"


.. _run_with_multipass:

Multipass
=========

`Multipass`_ is a cross-platform tool for launching Ubuntu VMs across Linux,
Windows, and macOS.

When a user launches a Multipass VM, user data can be passed by adding the
``--cloud-init`` flag and the appropriate YAML file containing the user data:

.. code-block:: shell-session

    $ multipass launch bionic --name test-vm --cloud-init userdata.yaml

Multipass will validate the user-data cloud-config file before attempting to
start the VM. This breaks all cloud-init configuration formats except user data
cloud-config.

.. _Multipass: https://multipass.run/
.. _LXD: https://ubuntu.com/lxd
.. _Libvirt: https://libvirt.org/
.. _QEMU: https://www.qemu.org/
.. _Instance Configuration: https://documentation.ubuntu.com/lxd/en/latest/instances/
.. _Custom Network Configuration: https://documentation.ubuntu.com/lxd/en/latest/cloud-init/
.. _cloud-utils: https://github.com/canonical/cloud-utils/
