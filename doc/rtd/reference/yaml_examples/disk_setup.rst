.. _cce-disk-setup:

Configure partitions and filesystems
************************************

Cloud-init supports the creation of simple partition tables and filesystems
on devices.

- Disk partitioning is done using the ``disk_setup`` directive.
- File system configuration is done using the ``fs_setup`` directive.

For a full list of keys, refer to the `disk setup module`_ schema.

General example
===============

.. literalinclude:: ../../../module-docs/cc_disk_setup/example1.yaml
   :language: yaml
   :linenos:

Partition a disk
================

The ``disk_setup`` directive instructs Cloud-init to partition a disk. The
format is:

.. code-block:: yaml

    #cloud-config
    disk_setup:
      ephemeral0:
        table_type: 'mbr'
        layout: true
      /dev/xvdh:
        table_type: 'mbr'
        layout:
          - 33
          - [33, 82]
          - 33
        overwrite: True

The format is a list of "dicts of dicts". The first value is the name of the
device and the subsequent values define how to create and lay out the
partition. The general format is:

.. code-block:: yaml

   disk_setup:
     <DEVICE>:
       table_type: 'mbr'
       layout: <LAYOUT|BOOL>
       overwrite: <BOOL>

Where:

- ``<DEVICE>``:
  The name of the device. ``ephemeralX`` and ``swap`` are special values which
  are specific to the cloud. For these devices, cloud-init will look up what
  the real device is and then use it.

  For other devices, the kernel device name is used. At this time, only simple
  kernel devices are supported, meaning that device mapper and other targets
  may not work.

  Note: There is currently no handling or setup of device mapper targets.

- ``table_type=<TYPE>``:
  Currently, the following are supported:

  - ``mbr``: (default) sets up an MS-DOS partition table
  - ``gpt``: sets up a GPT partition table

  Note: At this time only ``mbr`` and ``gpt`` partition tables are allowed.
  We anticipate that in the future we will also have ``RAID`` to create a
  ``mdadm`` RAID.

- ``layout={...}``:
  The device layout. This is a list of values, with the percentage of disk that
  the partition will take. Valid options are:

  - ``[<SIZE>, [<SIZE>, <PART_TYPE]]``

    Where ``<SIZE>`` is the **percentage** of the disk to use, while
    ``<PART_TYPE>`` is the numerical value of the partition type.

  The following sets up two partitions, with the first partition having a swap
  label, taking 1/3 of the disk space, and the remainder being used as the
  second partition: ::

   /dev/xvdh':
     table_type: 'mbr'
     layout:
       - [33,82]
       - 66
     overwrite: True

  - When layout is "true", it instructs cloud-init to single-partition the
    entire device.
  - When layout is "false" it means "don't partition" or "ignore existing
    partitioning".

  If layout is set to "true" and overwrite is set to "false", cloud-init will
  skip partitioning the device without a failure.

- ``overwrite=<BOOL>``: This describes whether to "ride with safetys on and
  everything holstered".

  - "false" is the default, which means that:

    1. The device will be checked for a partition table
    2. The device will be checked for a filesystem
    3. If either a partition of filesystem is found, then the operation will
       be **skipped**.

  - "true" is **cowboy mode**. There are no checks and things are done blindly.
    Use this option only with caution, you can do things you really, really
    don't want to do.

Set up the filesystem
=====================

``fs_setup`` describes the how the filesystems are supposed to look.

.. code-block:: yaml

    fs_setup:
      - label: ephemeral0
        filesystem: 'ext3'
        device: 'ephemeral0'
        partition: 'auto'
      - label: mylabl2
        filesystem: 'ext4'
        device: '/dev/xvda1'
      - cmd: mkfs -t %(filesystem)s -L %(label)s %(device)s
        label: mylabl3
        filesystem: 'btrfs'
        device: '/dev/xvdh'

The general format is:

.. code-block:: yaml

   fs_setup:
     - label: <LABEL>
       filesystem: <FS_TYPE>
       device: <DEVICE>
       partition: <PART_VALUE>
       overwrite: <OVERWRITE>
       replace_fs: <FS_TYPE>

Where:

- ``<LABEL>``:
  The filesystem label to be used. If set to "None", no label is used.

- ``<FS_TYPE>``:
  The filesystem type. It is assumed that the there will be a
  ``mkfs.<FS_TYPE>`` that behaves likes ``mkfs``. On a standard Ubuntu Cloud
  Image, this means that you have the option of ``ext{2,3,4}`` and ``vfat`` by
  default.

- ``<DEVICE>``:
  The device name. Special names of ``ephemeralX`` or ``swap`` are allowed and
  the actual device is acquired from the cloud datasource.

  When using ``ephemeralX`` (i.e. ``ephemeral0``), be sure to leave the label
  as ``ephemeralX`` or there may be issues with mounting the ephemeral storage
  layer.

  If you define the device as ``ephemeralX.Y`` then Y will be interpreted as a
  partition value. However, ``ephemeralX.0`` is the **same** as ``ephemeralX``.

- ``<PART_VALUE>``:
  Partition definitions are overwritten if you use the ``<DEVICE>.Y`` notation.
  The valid options are:

  - ``auto|any``:
    Tells cloud-init not to care if there is a partition or not.
    Auto will use the first partition that does not already contain a
    filesystem. In the absence of a partition table, it will put it directly
    on the disk.

  - ``auto``:
    If a filesystem that matches the specification (in terms of label),
    filesystem and device, then cloud-init will skip the filesystem creation.

  - ``any``:
    If a filesystem that matches the filesystem type and device, then
    cloud-init will skip the filesystem creation.

  Devices are selected based on first-detected, starting with partitions and
  then the raw disk. Consider the following: ::

           NAME     FSTYPE LABEL
           xvdb
           |-xvdb1  ext4
           |-xvdb2
           |-xvdb3  btrfs  test
           \-xvdb4  ext4   test

  If you ask for ``auto``, label of ``test``, and filesystem of ``ext4`` then
  cloud-init will select the 2nd partition, even though there is a partition
  match at the 4th partition.

  If you ask for ``any`` and a label of ``test``, then cloud-init will select
  the 1st partition.

  If you ask for ``auto`` and don't define label, then cloud-init will select
  the 1st partition.

  In general, if you have a specific partition configuration in mind, you
  should define either the device or the partition number. ``auto`` and ``any``
  are specifically intended for formatting ephemeral storage or for simple
  schemes.

- ``none``:
  Put the filesystem directly on the device.

- ``<NUM>``:
  Where ``NUM`` is the actual partition number.

- ``<OVERWRITE>``:
  Defines whether or not to overwrite any existing filesystem:

  - ``"true"``:
    Indiscriminately destroy any pre-existing filesystem. Use at your own risk.

  - ``"false"``:
    If a filesystem already exists, skip the creation.

- ``<REPLACE_FS>``:
  This is a special directive, used for Microsoft Azure, which instructs
  cloud-init to replace a filesystem of ``<FS_TYPE>``.

  Note that unless you define a label, this requires the use of the ``any``
  partition directive.

.. note::
   Expected behavior: The default behavior is to check if the filesystem
   exists. If a filesystem matches the specification, then the operation is a
   no-op.

.. _cce-resizefs:

Resize partitions and filesystems
=================================

These examples show how to resize a filesystem to use all available space on
the partition. The ``resizefs`` module can be used alongside the ``growpart``
module so that if the root partition is resized by ``growpart`` then the root
filesystem is also resized.

For a full list of keys, refer to the :ref:`resizefs module <mod_cc_resizefs>`
and the :ref:`growpart module <mod_cc_growpart>` schema.

Disable root filesystem resize operation
----------------------------------------

.. literalinclude:: ../../../module-docs/cc_resizefs/example1.yaml
   :language: yaml
   :linenos:

Run resize operation in background
----------------------------------

.. literalinclude:: ../../../module-docs/cc_resizefs/example2.yaml
   :language: yaml
   :linenos:

.. _cce-growpart:

Grow partitions
===============

For a full list of keys, refer to the :ref:`Growpart module <mod_cc_growpart>`
schema.

Example 1
---------

.. literalinclude:: ../../../module-docs/cc_growpart/example1.yaml
   :language: yaml
   :linenos:

Example 2
---------

.. literalinclude:: ../../../module-docs/cc_growpart/example2.yaml
   :language: yaml
   :linenos:


Cloud examples
==============

Default disk definitions for AWS
--------------------------------

This only works for non-NVME devices on supported instance types.

.. code-block:: yaml

    #cloud-config
    disk_setup:
      ephemeral0:
        table_type: 'mbr'
        layout: True
        overwrite: False
    fs_setup:
      - label: None,
        filesystem: ext3
        device: ephemeral0
        partition: auto

Default disk definitions for Microsoft Azure
--------------------------------------------

.. code-block:: yaml

    #cloud-config
    device_aliases: {'ephemeral0': '/dev/sdb'}
    disk_setup:
      ephemeral0:
        table_type: mbr
        layout: True
        overwrite: False
    fs_setup:
      - label: ephemeral0
        filesystem: ext4
        device: ephemeral0.1
        replace_fs: ntfs

Data disks definitions for Microsoft Azure
------------------------------------------

.. code-block:: yaml

    #cloud-config
    disk_setup:
      /dev/disk/azure/scsi1/lun0:
        table_type: gpt
        layout: True
        overwrite: True
    fs_setup:
      - device: /dev/disk/azure/scsi1/lun0
        partition: 1
        filesystem: ext4

Default disk definitions for SmartOS
------------------------------------

.. code-block:: yaml

    #cloud-config
    device_aliases: {'ephemeral0': '/dev/vdb'}
    disk_setup:
      ephemeral0:
        table_type: mbr
        layout: False
        overwrite: False
    fs_setup:
      - label: ephemeral0
        filesystem: ext4
        device: ephemeral0.0

.. note::
    For SmartOS, if the ephemeral disk is not defined, then the disk will
    not be automatically added to the mounts.

    The default definition is used to make sure that the ephemeral storage is
    setup properly.

.. LINKS
.. _disk setup module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#disk-setup
