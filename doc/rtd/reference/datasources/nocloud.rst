.. _datasource_nocloud:

NoCloud
*******

The data source ``NoCloud`` is a flexible datasource that can be used in
multiple different ways. With NoCloud, the user can provide user data and
metadata to the instance without running a network service (or even without
having a network at all). Alternatively, one may use a custom webserver to
provide configurations.

Configuration Methods:
======================

Method 1: Local filesystem, labeled filesystem
----------------------------------------------

To provide cloud-init configurations from the local filesystem, a labeled
`vfat`_ or `iso9660`_ filesystem containing user data and metadata may
be used. For this method to work, the filesystem volume must be labelled
``CIDATA``.

Method 2: Local filesystem, kernel commandline or SMBIOS
--------------------------------------------------------

Configuration files can be provided on the local filesystem without a label
using kernel commandline arguments or SMBIOS serial number to tell cloud-init
where on the filesystem to look.

Alternatively, one can provide metadata via the kernel command line or SMBIOS
"serial number" option. This argument might look like: ::

  ds=nocloud;s=file://path/to/directory/;h=node-42

Method 3: Custom webserver: kernel commandline or SMBIOS
--------------------------------------------------------

In a similar fashion, configuration files can be provided to cloud-init using a
custom webserver at a URL dictated by kernel commandline arguments or SMBIOS
serial number. This argument might look like: ::

  ds=nocloud;s=http://10.42.42.42/cloud-init/configs/

.. note::
   When supplementing kernel parameters in GRUB's boot menu take care to single-quote this full value to avoid GRUB interpreting the semi-colon as a reserved word. See: `GRUB quoting`_

Permitted keys
==============

The permitted keys are:

* ``h`` or ``local-hostname``
* ``i`` or ``instance-id``
* ``s`` or ``seedfrom``

A valid ``seedfrom`` value consists of:

Filesystem
----------

A filesystem path starting with ``/`` or ``file://`` that points to a directory
containing files: ``user-data``, ``meta-data``, and (optionally)
``vendor-data`` (a trailing ``/`` is required)

HTTP server
-----------

An ``http`` or ``https`` URL (a trailing ``/`` is required)


File formats
============

These user data and metadata files are required as separate files at the
same base URL: ::

  /user-data
  /meta-data

Both files must be present for it to be considered a valid seed ISO.

The ``user-data`` file uses :ref:`user data format<user_data_formats>` and
``meta-data`` is a YAML-formatted file representing what you'd find in the EC2
metadata service.

You may also optionally provide a vendor data file adhering to
:ref:`user data formats<user_data_formats>` at the same base URL: ::

  /vendor-data


DMI-specific kernel commandline
===============================

Cloud-init performs variable expansion of the ``seedfrom`` URL for any DMI
kernel variables present in :file:`/sys/class/dmi/id` (kenv on FreeBSD).
Your ``seedfrom`` URL can contain variable names of the format
``__dmi.varname__`` to indicate to the ``cloud-init`` NoCloud datasource that
``dmi.varname`` should be expanded to the value of the DMI system attribute
wanted.

.. list-table:: Available DMI variables for expansion in ``seedfrom`` URL
  :widths: 35 35 30
  :header-rows: 0

  * - ``dmi.baseboard-asset-tag``
    - ``dmi.baseboard-manufacturer``
    - ``dmi.baseboard-version``
  * - ``dmi.bios-release-date``
    - ``dmi.bios-vendor``
    - ``dmi.bios-version``
  * - ``dmi.chassis-asset-tag``
    - ``dmi.chassis-manufacturer``
    - ``dmi.chassis-serial-number``
  * - ``dmi.chassis-version``
    - ``dmi.system-manufacturer``
    - ``dmi.system-product-name``
  * - ``dmi.system-serial-number``
    - ``dmi.system-uuid``
    - ``dmi.system-version``

For example, you can pass this option to QEMU: ::

  -smbios type=1,serial=ds=nocloud;s=http://10.10.0.1:8000/__dmi.chassis-serial-number__/

This will cause NoCloud to fetch the full metadata from a URL based on
YOUR_SERIAL_NUMBER as seen in :file:`/sys/class/dmi/id/chassis_serial_number`
(kenv on FreeBSD) from http://10.10.0.1:8000/YOUR_SERIAL_NUMBER/meta-data after
the network initialisation is complete.


Example: Creating a disk
========================

Given a disk Ubuntu cloud image in :file:`disk.img`, you can create a
sufficient disk by following the following example.

1. Create the :file:`user-data` and :file:`meta-data` files that will be used
   to modify the image on first boot.

.. code-block:: sh

   $ echo -e "instance-id: iid-local01\nlocal-hostname: cloudimg" > meta-data
   $ echo -e "#cloud-config\npassword: passw0rd\nchpasswd: { expire: False }\nssh_pwauth: True\n" > user-data

2. At this stage you have three options:

   a. Create a disk to attach with some user data and metadata:

      .. code-block:: sh

         $ genisoimage  -output seed.iso -volid cidata -joliet -rock user-data meta-data

   b. Alternatively, create a ``vfat`` filesystem with the same files:

      .. code-block:: sh

         $ truncate --size 2M seed.iso
         $ mkfs.vfat -n cidata seed.iso

      * 2b) Option 1: mount and copy files:

        .. code-block:: sh

           $ sudo mount -t vfat seed.iso /mnt
           $ sudo cp user-data meta-data /mnt
           $ sudo umount /mnt

      * 2b) Option 2: the ``mtools`` package provides ``mcopy``, which can
        access ``vfat`` filesystems without mounting them:

        .. code-block::

           $ mcopy -oi seed.iso user-data meta-data ::

3. Create a new qcow image to boot, backed by your original image:

.. code-block:: sh

   $ qemu-img create -f qcow2 -b disk.img -F qcow2 boot-disk.img

4. Boot the image and log in as "Ubuntu" with password "passw0rd":

.. code-block:: sh

   $ kvm -m 256 \
      -net nic -net user,hostfwd=tcp::2222-:22 \
      -drive file=boot-disk.img,if=virtio \
      -drive driver=raw,file=seed.iso,if=virtio

.. note::
   Note that "passw0rd" was set as password through the user data above. There
   is no password set on these images.

.. note::
   The ``instance-id`` provided (``iid-local01`` above) is what is used to
   determine if this is "first boot". So, if you are making updates to
   user data you will also have to change the ``instance-id``, or start the
   disk fresh.

Also, you can inject an :file:`/etc/network/interfaces` file by providing the
content for that file in the ``network-interfaces`` field of
:file:`meta-data`.

Example ``meta-data``
---------------------

::

    instance-id: iid-abcdefg
    network-interfaces: |
      iface eth0 inet static
      address 192.168.1.10
      network 192.168.1.0
      netmask 255.255.255.0
      broadcast 192.168.1.255
      gateway 192.168.1.254
    hostname: myhost


Network configuration can also be provided to ``cloud-init`` in either
:ref:`network_config_v1` or :ref:`network_config_v2` by providing that
YAML formatted data in a file named :file:`network-config`. If found,
this file will override a :file:`network-interfaces` file.

See an example below. Note specifically that this file does not
have a top level ``network`` key as it is already assumed to
be network configuration based on the filename.

Example config
--------------

.. code-block:: yaml

   version: 1
   config:
      - type: physical
        name: interface0
        mac_address: "52:54:00:12:34:00"
        subnets:
           - type: static
             address: 192.168.1.10
             netmask: 255.255.255.0
             gateway: 192.168.1.254


.. code-block:: yaml

   version: 2
   ethernets:
     interface0:
       match:
         macaddress: "52:54:00:12:34:00"
       set-name: interface0
       addresses:
         - 192.168.1.10/255.255.255.0
       gateway4: 192.168.1.254


.. _iso9660: https://en.wikipedia.org/wiki/ISO_9660
.. _vfat: https://en.wikipedia.org/wiki/File_Allocation_Table
.. _GRUB quoting: https://www.gnu.org/software/grub/manual/grub/grub.html#Quoting
