.. _launch_qemu:

Run cloud-init locally with QEMU
********************************

`QEMU`_ is a general purpose computer hardware emulator, able to run virtual
machines with hardware acceleration, and to emulate the instruction sets of
different architectures than the host you are running on.

The ``NoCloud`` datasource allows you to provide your own user data,
metadata, or network configuration directly to an instance without running a
network service. This is helpful for launching local cloud images with QEMU.

Create your configuration
-------------------------

.. include:: shared/create_config.txt

Create an ISO disk
------------------

This disk is used to pass the configuration files to cloud-init. Create it with
the ``genisoimage`` command:

.. code-block:: shell-session

    genisoimage \
        -output seed.img \
        -volid cidata -rational-rock -joliet \
        user-data meta-data network-config

Download a cloud image
----------------------

.. include:: shared/download_image.txt

.. note::
   This example uses emulated CPU instructions on non-x86 hosts, so it may be
   slow. To make it faster on non-x86 architectures, one can change the image
   type and ``qemu-system-<arch>`` command name to match the
   architecture of your host machine.

Boot the image with the ISO attached
------------------------------------

Boot the cloud image with our configuration, ``seed.img``, to QEMU:

.. code-block:: shell-session

    $ qemu-system-x86_64 -m 1024 -net nic -net user \
        -drive file=jammy-server-cloudimg-amd64.img,index=0,format=qcow2,media=disk \
        -drive file=seed.img,index=1,media=cdrom \
        -machine accel=kvm:tcg

The now-booted image will allow for login using the password provided above.

For additional configuration, you can provide much more detailed
configuration in the empty :file:`network-config` and :file:`meta-data` files.

.. note::
    See the :ref:`network_config_v2` page for details on the format and config
    of network configuration. To learn more about the possible values for
    metadata, check out the :ref:`datasource_nocloud` page.

.. LINKS
.. _QEMU: https://www.qemu.org/
