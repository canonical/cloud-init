.. _datasource_nocloud:

NoCloud
*******

The data source ``NoCloud`` is a flexible datasource that can be used in
multiple different ways. With NoCloud, one can provide configurations to
the instance without running a network service (or even without having a
network at all). Alternatively, one can use HTTP/HTTPS or FTP/FTPS to provide
a configuration.

Configuration Methods:
======================

.. warning::
    User data placed under ``/etc/cloud/`` will **not** be recognized as a
    source of configuration data by the NoCloud datasource. While it may
    be acted upon by cloud-init, using
    :ref:`DataSourceNone<datasource_none_example>` should be preferred.

Method 1: Labeled filesystem
----------------------------

A labeled `vfat`_ or `iso9660` filesystem may be used. The filesystem volume
must be labelled ``CIDATA``.


Method 2: Custom webserver
--------------------------

Configuration files can be provided to cloud-init over HTTP(s). To tell
cloud-init the URI to use, arguments must be passed to the instance via the
kernel command line or SMBIOS serial number. This argument might look like: ::

  ds=nocloud;s=https://10.42.42.42/cloud-init/configs/

.. note::
   If using kernel command line arguments with GRUB, note that an
   unescaped semicolon is intepreted as the end of a statement.
   Consider using single-quotes to avoid this pitfall. See: `GRUB quoting`_
   ds=nocloud;s=http://10.42.42.42/cloud-init/configs/

Alternatively, this URI may be defined in a configuration in a file
:file:`/etc/cloud/cloud.cfg.d/*.cfg` like this: ::

  datasource:
    NoCloud:
      seedfrom: https://10.42.42.42/cloud-init/configs/

Method 3: FTP Server
--------------------

Configuration files can be provided to cloud-init over unsecured FTP
or alternatively with FTP over TLS. To tell cloud-init the URL to use,
arguments must be passed to the instance via the kernel command line or SMBIOS
serial number. This argument might look like: ::

  ds=nocloud;s=ftps://10.42.42.42/cloud-init/configs/

Alternatively, this URI may be defined in a configuration in a file
:file:`/etc/cloud/cloud.cfg.d/*.cfg` like this: ::

  datasource:
    NoCloud:
      seedfrom: ftps://10.42.42.42/cloud-init/configs/

Method 4: Local filesystem
--------------------------

Configuration files can be provided on the local filesystem at specific
filesystem paths using kernel command line arguments or SMBIOS serial number to
tell cloud-init where on the filesystem to look.

.. note::
   Unless arbitrary filesystem paths are required, one might prefer to use
   :ref:`DataSourceNone<datasource_none_example>`, since it does not require
   modifying the kernel command line or SMBIOS.

This argument might look like: ::

  ds=nocloud;s=file://path/to/directory/

Alternatively, this URI may be defined in a configuration in a file
:file:`/etc/cloud/cloud.cfg.d/*.cfg` like this: ::

  datasource:
    NoCloud:
      seedfrom: file://10.42.42.42/cloud-init/configs/


Permitted keys
==============

Currently three keys (and their aliases) are permitted for configuring
cloud-init.

The only required key is:

* ``seedfrom`` alias: ``s``

A valid ``seedfrom`` value consists of a URI which must contain a trailing
``/``.

Some optional keys may be used, but their use is discouraged and may
be removed in the future.

* ``local-hostname`` alias: ``h`` (:ref:`cloud-config<mod_cc_set_hostname>`
  preferred)
* ``instance-id`` alias: ``i``  (set instance id  in :file:`meta-data` instead)

.. note::

   The aliases ``s`` , ``h`` and ``i`` are only supported by kernel
   command line or SMBIOS. When configured in a ``*.cfg`` file, the long key
   name is required.

Seedfrom: HTTP and HTTPS
------------------------

The URI elements supported by NoCloud's HTTP and HTTPS implementations
include: ::

   <scheme>://<host>/<path>/

Where ``scheme`` can be ``http`` or ``https`` and ``host`` can be an IP
address or DNS name.

Seedfrom: FTP and FTP over TLS
------------------------------

The URI elements supported by NoCloud's FTP and FTPS implementation
include: ::

   <scheme>://<userinfo>@<host>:<port>/<path>/

Where ``scheme`` can be ``ftp`` or ``ftps``, ``userinfo`` will be
``username:password`` (defaults is ``anonymous`` and an empty password),
``host`` can be an IP address or DNS name, and ``port`` is which network
port to use (default is ``21``).

Seedfrom: Files
---------------

The path pointed to by the URI can contain the following
files:

``user-data`` (required)
``meta-data`` (required)
``vendor-data`` (optional)
``network-config`` (optional)

If the seedfrom URI doesn't contain the required files, this datasource
will be skipped.

The ``user-data`` file uses :ref:`user data format<user_data_formats>`. The
``meta-data`` file is a YAML-formatted file.

The ``vendor-data`` file adheres to
:ref:`user data formats<user_data_formats>`. The ``network-config`` file
follows cloud-init's :ref:`Network Configuration Formats<network_config_v2>`.

DMI-specific kernel command line
================================

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
   $ echo -e "#cloud-config\npassword: passw0rd\nchpasswd: { expire: False }\nssh_pwauth: True\ncreate_hostname_file: true\n" > user-data

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
