.. _datasource_nocloud:

NoCloud
*******

The data source ``NoCloud`` is a flexible datasource that can be used in
multiple different ways.

With NoCloud, one can provide configuration to the instance locally (without
network access) or alternatively NoCloud can fetch the configuration from a
remote server.

Much of the following documentation describes how to tell cloud-init where
to get its configuration.

Runtime configurations
======================

Cloud-init discovers four types of configuration at runtime. The source of
these configuration types is configurable with a discovery configuration. This
discovery configuration can be delivered to cloud-init in different ways, but
is different from the configurations that cloud-init uses to configure the
instance at runtime.

user-data
---------

User-data is a :ref:`configuration format<user_data_formats>` that allows a
user to configure an instance.

meta-data
---------

The ``meta-data`` file is a YAML-formatted file which contains cloud-provided
information to the instance. This is required to contain an ``instance-id``,
with other cloud-specific keys available.

vendor-data
-----------

Vendor-data may be used to provide default cloud-specific configurations which
may be overridden by user-data. This may be useful, for example, to configure
an instance with a cloud provider's repository mirror for faster package
installation.

network-config
--------------

Network configuration typically comes from the cloud provider to set
cloud-specific network configurations, or a reasonable default is set by
cloud-init (typically cloud-init brings up an interface using DHCP).

Since NoCloud is a generic datasource, network configuration may be set the
same way as user-data, meta-data, vendor-data.

See the :ref:`network configuration<network_config>` documentation for
information on network configuration formats.

Discovery configuration
=======================

The purpose of the discovery configuration is to tell cloud-init where it can
find the runtime configurations described above.

There are two methods for cloud-init to receive a discovery configuration.

Method 1: Line configuration
----------------------------

The "line configuration" is a single string of text which is passed to an
instance at boot time via either the kernel command line or in the serial
number exposed via DMI (sometimes called SMBIOS).

Example: ::

  ds=nocloud;s=https://10.42.42.42/configs/

In the above line configuration, ``ds=nocloud`` tells cloud-init to use the
NoCloud datasource, and ``s=https://10.42.42.42/configs/`` tells cloud-init to
fetch configurations using ``https`` from the URI
``https://10.42.42.42/configs/``.

We will describe the possible values in a line configuration in the following
sections. See :ref:`this section<line_config_detail>` for more details on line
configuration.

.. note::

   If using kernel command line arguments with GRUB, note that an
   unescaped semicolon is interpreted as the end of a statement.
   See: `GRUB quoting`_

Method 2: System configuration
------------------------------

System configurations are YAML-formatted files and have names that end in
``.cfg``. These are located under :file:`/etc/cloud/cloud.cfg.d/`.

Example:

.. code-block:: yaml

   datasource:
     NoCloud:
       seedfrom: https://10.42.42.42/configs/

The above system configuration tells cloud-init that it is using NoCloud and
that it can find configurations at ``https://10.42.42.42/configs/``.

The scope of this section is limited to its use for selecting the source of
its configuration, however it is worth mentioning that the system configuration
provides more than just the discovery configuration.

In addition to defining where cloud-init can find runtime configurations, the
system configuration also controls many of cloud-init's default behaviors.
Most users shouldn't need to modify these defaults, however it is worth noting
that downstream distributions often use them to set reasonable default
behaviors for cloud-init. This includes things such as which distro to behave
as and which networking backend to use.

The default values in :file:`/etc/cloud/cloud.cfg` may be overridden by drop-in
files which are stored in :file:`/etc/cloud/cloud.cfg.d`.

Configuration sources
=====================

User-data, meta-data, network config, and vendor-data may be sourced from one
of several possible locations, either locally or remotely.

Source 1: Local filesystem
--------------------------

System configuration may provide cloud-init runtime configuration directly

.. code-block:: yaml

   datasource:
     NoCloud:
       meta-data: |
         instance-id: l-eadfbe
       user-data: |
         #cloud-config
         runcmd: [ echo "it worked!" > /tmp/example.txt ]

Local filesystem: custom location
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Cloud-init makes it possible to find system configuration in a custom
filesystem path for those that require more flexibility. This may be
done with a line configuration: ::


  ds=nocloud;s=file:///path/to/directory/

Or a system configuration:

.. code-block:: yaml

   datasource:
     NoCloud:
       seedfrom: file:///path/to/directory

Source 2: Drive with labeled filesystem
---------------------------------------

A labeled `vfat`_ or `iso9660` filesystem may be used. The filesystem volume
must be labelled ``CIDATA``. The :ref:`configuration files<source_files>` must
be in the root directory of the filesystem.

Source 3: Custom webserver
--------------------------

Configuration files can be provided to cloud-init over HTTP(S) using a
line configuration: ::

  ds=nocloud;s=https://10.42.42.42/cloud-init/configs/

or using system configuration:

.. code-block:: yaml

  datasource:
    NoCloud:
      seedfrom: https://10.42.42.42/cloud-init/configs/

Source 4: FTP Server
--------------------

Configuration files can be provided to cloud-init over unsecured FTP
or alternatively with FTP over TLS using a line configuration ::

  ds=nocloud;s=ftps://10.42.42.42/cloud-init/configs/

or using system configuration

.. code-block:: yaml

  datasource:
    NoCloud:
      seedfrom: ftps://10.42.42.42/cloud-init/configs/

.. _source_files:

Source files
------------

The base path pointed to by the URI in the above sources provides content
using the following final path components:

* ``user-data``
* ``meta-data``
* ``vendor-data``
* ``network-config``

For example, if the ``seedfrom`` value of ``seedfrom`` is
``https://10.42.42.42/``, then the following files will be fetched from the
webserver at first boot:

.. code-block:: sh

    https://10.42.42.42/user-data
    https://10.42.42.42/vendor-data
    https://10.42.42.42/meta-data
    https://10.42.42.42/network-config

If the required files don't exist, this datasource will be skipped.

.. _line_config_detail:

Line configuration in detail
============================

The line configuration has several options.

Permitted keys (DMI and kernel command line)
--------------------------------------------

Currently three keys (and their aliases) are permitted in cloud-init's kernel
command line and DMI (sometimes called SMBIOS) serial number.

There is only one required key in a line configuration:

* ``seedfrom`` (alternatively ``s``)

A valid ``seedfrom`` value consists of a URI which must contain a trailing
``/``.

Some optional keys may be used, but their use is discouraged and may
be removed in the future.


* ``local-hostname`` (alternatively ``h``)
* ``instance-id`` (alternatively ``i``)

Both of these can be set in :file:`meta-data` instead.

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

Discovery configuration considerations
======================================

Above, we describe the two methods of providing discovery configuration (system
configuration and line configuration). Two methods exist because there are
advantages and disadvantages to each option, neither is clearly a better
choice - so it is left to the user to decide.

Line configuration
------------------

**Advantages**

* it may be possible to set kernel command line and DMI variables at boot time
  without modifying the base image

**Disadvantages**

* requires control and modification of the hypervisor or the bootloader
* DMI / SMBIOS is architecture specific

System configuration
--------------------

**Advantages**

* simple: requires only modifying a file

**Disadvantages**

* requires modifying the filesystem prior to booting an instance

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

For example, you can pass this line configuration to QEMU: ::

  -smbios type=1,serial=ds=nocloud;s=http://10.10.0.1:8000/__dmi.chassis-serial-number__/

This will cause NoCloud to fetch all data from a URL based on
YOUR_SERIAL_NUMBER as seen in :file:`/sys/class/dmi/id/chassis_serial_number`
(kenv on FreeBSD) from http://10.10.0.1:8000/YOUR_SERIAL_NUMBER/ after
the network initialization is complete.


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

   a. Create a disk to attach with some user-data and meta-data:

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
   Note that "passw0rd" was set as password through the user-data above. There
   is no password set on these images.

.. note::
   The ``instance-id`` provided (``iid-local01`` above) is what is used to
   determine if this is "first boot". So, if you are making updates to
   user-data you will also have to change the ``instance-id``, or start the
   disk fresh.

Example ``meta-data``
---------------------

.. code-block:: yaml

    instance-id: iid-abcdefg
    network-interfaces: |
      iface eth0 inet static
      address 192.168.1.10
      network 192.168.1.0
      netmask 255.255.255.0
      broadcast 192.168.1.255
      gateway 192.168.1.254
    hostname: myhost


``network-config``
------------------

Network configuration can also be provided to ``cloud-init`` in either
:ref:`network_config_v1` or :ref:`network_config_v2` by providing that
YAML formatted data in a file named :file:`network-config`.

Example network v1:

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


Example network v2:

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
