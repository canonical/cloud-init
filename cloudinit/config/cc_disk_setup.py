# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Disk Setup
----------
**Summary:** configure partitions and filesystems

This module is able to configure simple partition tables and filesystems.

.. note::
    for more detail about configuration options for disk setup, see the disk
    setup example

For convenience, aliases can be specified for disks using the
``device_aliases`` config key, which takes a dictionary of alias: path
mappings. There are automatic aliases for ``swap`` and ``ephemeral<X>``, where
``swap`` will always refer to the active swap partition and ``ephemeral<X>``
will refer to the block device of the ephemeral image.

Disk partitioning is done using the ``disk_setup`` directive. This config
directive accepts a dictionary where each key is either a path to a block
device or an alias specified in ``device_aliases``, and each value is the
configuration options for the device. The ``table_type`` option specifies the
partition table type, either ``mbr`` or ``gpt``. The ``layout`` option
specifies how partitions on the device are to be arranged. If ``layout`` is set
to ``true``, a single partition using all the space on the device will be
created. If set to ``false``, no partitions will be created. Partitions can be
specified by providing a list to ``layout``, where each entry in the list is
either a size or a list containing a size and the numerical value for a
partition type. The size for partitions is specified in **percentage** of disk
space, not in bytes (e.g. a size of 33 would take up 1/3 of the disk space).
The ``overwrite`` option controls whether this module tries to be safe about
writing partition talbes or not. If ``overwrite: false`` is set, the device
will be checked for a partition table and for a file system and if either is
found, the operation will be skipped. If ``overwrite: true`` is set, no checks
will be performed.

.. note::
    Using ``overwrite: true`` is dangerous and can lead to data loss, so double
    check that the correct device has been specified if using this option.

File system configuration is done using the ``fs_setup`` directive. This config
directive accepts a list of filesystem configs. The device to create the
filesystem on may be specified either as a path or as an alias in the format
``<alias name>.<y>`` where ``<y>`` denotes the partition number on the device.
The partition can also be specified by setting ``partition`` to the desired
partition number. The ``partition`` option may also be set to ``auto``, in
which this module will search for the existance of a filesystem matching the
``label``, ``type`` and ``device`` of the ``fs_setup`` entry and will skip
creating the filesystem if one is found. The ``partition`` option may also be
set to ``any``, in which case any file system that matches ``type`` and
``device`` will cause this module to skip filesystem creation for the
``fs_setup`` entry, regardless of ``label`` matching or not. To write a
filesystem directly to a device, use ``partition: none``. A label can be
specified for the filesystem using ``label``, and the filesystem type can be
specified using ``filesystem``.

.. note::
    If specifying device using the ``<device name>.<partition number>`` format,
    the value of ``partition`` will be overwritten.

.. note::
    Using ``overwrite: true`` for filesystems is dangerous and can lead to data
    loss, so double check the entry in ``fs_setup``.

.. note::
    ``replace_fs`` is ignored unless ``partition`` is ``auto`` or ``any``.

**Internal name:** ``cc_disk_setup``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    device_aliases:
        <alias name>: <device path>
    disk_setup:
        <alias name/path>:
            table_type: <'mbr'/'gpt'>
            layout:
                - [33,82]
                - 66
            overwrite: <true/false>
    fs_setup:
        - label: <label>
          filesystem: <filesystem type>
          device: <device>
          partition: <"auto"/"any"/"none"/<partition number>>
          overwrite: <true/false>
          replace_fs: <filesystem type>
"""

from cloudinit.settings import PER_INSTANCE
from cloudinit import util
import logging
import os
import shlex

frequency = PER_INSTANCE

# Define the commands to use
UDEVADM_CMD = util.which('udevadm')
SFDISK_CMD = util.which("sfdisk")
SGDISK_CMD = util.which("sgdisk")
LSBLK_CMD = util.which("lsblk")
BLKID_CMD = util.which("blkid")
BLKDEV_CMD = util.which("blockdev")
WIPEFS_CMD = util.which("wipefs")

LANG_C_ENV = {'LANG': 'C'}

LOG = logging.getLogger(__name__)


def handle(_name, cfg, cloud, log, _args):
    """
    See doc/examples/cloud-config-disk-setup.txt for documentation on the
    format.
    """
    disk_setup = cfg.get("disk_setup")
    if isinstance(disk_setup, dict):
        update_disk_setup_devices(disk_setup, cloud.device_name_to_device)
        log.debug("Partitioning disks: %s", str(disk_setup))
        for disk, definition in disk_setup.items():
            if not isinstance(definition, dict):
                log.warning("Invalid disk definition for %s" % disk)
                continue

            try:
                log.debug("Creating new partition table/disk")
                util.log_time(logfunc=LOG.debug,
                              msg="Creating partition on %s" % disk,
                              func=mkpart, args=(disk, definition))
            except Exception as e:
                util.logexc(LOG, "Failed partitioning operation\n%s" % e)

    fs_setup = cfg.get("fs_setup")
    if isinstance(fs_setup, list):
        log.debug("setting up filesystems: %s", str(fs_setup))
        update_fs_setup_devices(fs_setup, cloud.device_name_to_device)
        for definition in fs_setup:
            if not isinstance(definition, dict):
                log.warning("Invalid file system definition: %s" % definition)
                continue

            try:
                log.debug("Creating new filesystem.")
                device = definition.get('device')
                util.log_time(logfunc=LOG.debug,
                              msg="Creating fs for %s" % device,
                              func=mkfs, args=(definition,))
            except Exception as e:
                util.logexc(LOG, "Failed during filesystem operation\n%s" % e)


def update_disk_setup_devices(disk_setup, tformer):
    # update 'disk_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for origname in disk_setup.keys():
        transformed = tformer(origname)
        if transformed is None or transformed == origname:
            continue
        if transformed in disk_setup:
            LOG.info("Replacing %s in disk_setup for translation of %s",
                     origname, transformed)
            del disk_setup[transformed]

        disk_setup[transformed] = disk_setup[origname]
        disk_setup[transformed]['_origname'] = origname
        del disk_setup[origname]
        LOG.debug("updated disk_setup device entry '%s' to '%s'",
                  origname, transformed)


def update_fs_setup_devices(disk_setup, tformer):
    # update 'fs_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for definition in disk_setup:
        if not isinstance(definition, dict):
            LOG.warning("entry in disk_setup not a dict: %s", definition)
            continue

        origname = definition.get('device')

        if origname is None:
            continue

        (dev, part) = util.expand_dotted_devname(origname)

        tformed = tformer(dev)
        if tformed is not None:
            dev = tformed
            LOG.debug("%s is mapped to disk=%s part=%s",
                      origname, tformed, part)
            definition['_origname'] = origname
            definition['device'] = tformed

        if part:
            # In origname with <dev>.N, N overrides 'partition' key.
            if 'partition' in definition:
                LOG.warning("Partition '%s' from dotted device name '%s' "
                            "overrides 'partition' key in %s", part, origname,
                            definition)
                definition['_partition'] = definition['partition']
            definition['partition'] = part


def value_splitter(values, start=None):
    """
    Returns the key/value pairs of output sent as string
    like:  FOO='BAR' HOME='127.0.0.1'
    """
    _values = shlex.split(values)
    if start:
        _values = _values[start:]

    for key, value in [x.split('=') for x in _values]:
        yield key, value


def enumerate_disk(device, nodeps=False):
    """
    Enumerate the elements of a child device.

    Parameters:
        device: the kernel device name
        nodeps <BOOL>: don't enumerate children devices

    Return a dict describing the disk:
        type: the entry type, i.e disk or part
        fstype: the filesystem type, if it exists
        label: file system label, if it exists
        name: the device name, i.e. sda
    """

    lsblk_cmd = [LSBLK_CMD, '--pairs', '--output', 'NAME,TYPE,FSTYPE,LABEL',
                 device]

    if nodeps:
        lsblk_cmd.append('--nodeps')

    info = None
    try:
        info, _err = util.subp(lsblk_cmd)
    except Exception as e:
        raise Exception("Failed during disk check for %s\n%s" % (device, e))

    parts = [x for x in (info.strip()).splitlines() if len(x.split()) > 0]

    for part in parts:
        d = {
            'name': None,
            'type': None,
            'fstype': None,
            'label': None,
        }

        for key, value in value_splitter(part):
            d[key.lower()] = value

        yield d


def device_type(device):
    """
    Return the device type of the device by calling lsblk.
    """

    for d in enumerate_disk(device, nodeps=True):
        if "type" in d:
            return d["type"].lower()
    return None


def is_device_valid(name, partition=False):
    """
    Check if the device is a valid device.
    """
    d_type = ""
    try:
        d_type = device_type(name)
    except Exception:
        LOG.warning("Query against device %s failed", name)
        return False

    if partition and d_type == 'part':
        return True
    elif not partition and d_type == 'disk':
        return True
    return False


def check_fs(device):
    """
    Check if the device has a filesystem on it

    Output of blkid is generally something like:
    /dev/sda: LABEL="Backup500G" UUID="..." TYPE="ext4"

    Return values are device, label, type, uuid
    """
    out, label, fs_type, uuid = None, None, None, None

    blkid_cmd = [BLKID_CMD, '-c', '/dev/null', device]
    try:
        out, _err = util.subp(blkid_cmd, rcs=[0, 2])
    except Exception as e:
        raise Exception("Failed during disk check for %s\n%s" % (device, e))

    if out:
        if len(out.splitlines()) == 1:
            for key, value in value_splitter(out, start=1):
                if key.lower() == 'label':
                    label = value
                elif key.lower() == 'type':
                    fs_type = value
                elif key.lower() == 'uuid':
                    uuid = value

    return label, fs_type, uuid


def is_filesystem(device):
    """
    Returns true if the device has a file system.
    """
    _, fs_type, _ = check_fs(device)
    return fs_type


def find_device_node(device, fs_type=None, label=None, valid_targets=None,
                     label_match=True, replace_fs=None):
    """
    Find a device that is either matches the spec, or the first

    The return is value is (<device>, <bool>) where the device is the
    device to use and the bool is whether the device matches the
    fs_type and label.

    Note: This works with GPT partition tables!
    """
    # label of None is same as no label
    if label is None:
        label = ""

    if not valid_targets:
        valid_targets = ['disk', 'part']

    raw_device_used = False
    for d in enumerate_disk(device):

        if d['fstype'] == replace_fs and label_match is False:
            # We found a device where we want to replace the FS
            return ('/dev/%s' % d['name'], False)

        if (d['fstype'] == fs_type and
                ((label_match and d['label'] == label) or not label_match)):
            # If we find a matching device, we return that
            return ('/dev/%s' % d['name'], True)

        if d['type'] in valid_targets:

            if d['type'] != 'disk' or d['fstype']:
                raw_device_used = True

            if d['type'] == 'disk':
                # Skip the raw disk, its the default
                pass

            elif not d['fstype']:
                return ('/dev/%s' % d['name'], False)

    if not raw_device_used:
        return (device, False)

    LOG.warning("Failed to find device during available device search.")
    return (None, False)


def is_disk_used(device):
    """
    Check if the device is currently used. Returns true if the device
    has either a file system or a partition entry
    is no filesystem found on the disk.
    """

    # If the child count is higher 1, then there are child nodes
    # such as partition or device mapper nodes
    if len(list(enumerate_disk(device))) > 1:
        return True

    # If we see a file system, then its used
    _, check_fstype, _ = check_fs(device)
    if check_fstype:
        return True

    return False


def get_dyn_func(*args):
    """
    Call the appropriate function.

    The first value is the template for function name
    The second value is the template replacement
    The remain values are passed to the function

    For example: get_dyn_func("foo_%s", 'bar', 1, 2, 3,)
        would call "foo_bar" with args of 1, 2, 3
    """
    if len(args) < 2:
        raise Exception("Unable to determine dynamic funcation name")

    func_name = (args[0] % args[1])
    func_args = args[2:]

    try:
        if func_args:
            return globals()[func_name](*func_args)
        else:
            return globals()[func_name]

    except KeyError:
        raise Exception("No such function %s to call!" % func_name)


def get_hdd_size(device):
    try:
        size_in_bytes, _ = util.subp([BLKDEV_CMD, '--getsize64', device])
        sector_size, _ = util.subp([BLKDEV_CMD, '--getss', device])
    except Exception as e:
        raise Exception("Failed to get %s size\n%s" % (device, e))

    return int(size_in_bytes) / int(sector_size)


def check_partition_mbr_layout(device, layout):
    """
    Returns true if the partition layout matches the one on the disk

    Layout should be a list of values. At this time, this only
    verifies that the number of partitions and their labels is correct.
    """

    read_parttbl(device)
    prt_cmd = [SFDISK_CMD, "-l", device]
    try:
        out, _err = util.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise Exception("Error running partition command on %s\n%s" % (
                        device, e))

    found_layout = []
    for line in out.splitlines():
        _line = line.split()
        if len(_line) == 0:
            continue

        if device in _line[0]:
            # We don't understand extended partitions yet
            if _line[-1].lower() in ['extended', 'empty']:
                continue

            # Find the partition types
            type_label = None
            for x in sorted(range(1, len(_line)), reverse=True):
                if _line[x].isdigit() and _line[x] != '/':
                    type_label = _line[x]
                    break

            found_layout.append(type_label)
    return found_layout


def check_partition_gpt_layout(device, layout):
    prt_cmd = [SGDISK_CMD, '-p', device]
    try:
        out, _err = util.subp(prt_cmd, update_env=LANG_C_ENV)
    except Exception as e:
        raise Exception("Error running partition command on %s\n%s" % (
                        device, e))

    out_lines = iter(out.splitlines())
    # Skip header.  Output looks like:
    # ***************************************************************
    # Found invalid GPT and valid MBR; converting MBR to GPT format
    # in memory.
    # ***************************************************************
    #
    # Disk /dev/vdb: 83886080 sectors, 40.0 GiB
    # Logical sector size: 512 bytes
    # Disk identifier (GUID): 8A7F11AD-3953-491B-8051-077E01C8E9A7
    # Partition table holds up to 128 entries
    # First usable sector is 34, last usable sector is 83886046
    # Partitions will be aligned on 2048-sector boundaries
    # Total free space is 83476413 sectors (39.8 GiB)
    #
    # Number Start (sector) End (sector) Size       Code  Name
    # 1      2048           206847       100.0 MiB  0700  Microsoft basic data
    for line in out_lines:
        if line.strip().startswith('Number'):
            break

    codes = [line.strip().split()[5] for line in out_lines]
    cleaned = []

    # user would expect a code '83' to be Linux, but sgdisk outputs 8300.
    for code in codes:
        if len(code) == 4 and code.endswith("00"):
            code = code[0:2]
        cleaned.append(code)
    return cleaned


def check_partition_layout(table_type, device, layout):
    """
    See if the partition lay out matches.

    This is future a future proofing function. In order
    to add support for other disk layout schemes, add a
    function called check_partition_%s_layout
    """
    found_layout = get_dyn_func(
        "check_partition_%s_layout", table_type, device, layout)

    LOG.debug("called check_partition_%s_layout(%s, %s), returned: %s",
              table_type, device, layout, found_layout)
    if isinstance(layout, bool):
        # if we are using auto partitioning, or "True" be happy
        # if a single partition exists.
        if layout and len(found_layout) >= 1:
            return True
        return False

    elif len(found_layout) == len(layout):
        # This just makes sure that the number of requested
        # partitions and the type labels are right
        layout_types = [str(x[1]) if isinstance(x, (tuple, list)) else None
                        for x in layout]
        LOG.debug("Layout types=%s. Found types=%s",
                  layout_types, found_layout)
        for itype, ftype in zip(layout_types, found_layout):
            if itype is not None and str(ftype) != str(itype):
                return False
        return True

    return False


def get_partition_mbr_layout(size, layout):
    """
    Calculate the layout of the partition table. Partition sizes
    are defined as percentage values or a tuple of percentage and
    partition type.

    For example:
        [ 33, [66: 82] ]

    Defines the first partition to be a size of 1/3 the disk,
    while the remaining 2/3's will be of type Linux Swap.
    """

    if not isinstance(layout, list) and isinstance(layout, bool):
        # Create a single partition
        return "0,"

    if ((len(layout) == 0 and isinstance(layout, list)) or
            not isinstance(layout, list)):
        raise Exception("Partition layout is invalid")

    last_part_num = len(layout)
    if last_part_num > 4:
        raise Exception("Only simply partitioning is allowed.")

    part_definition = []
    part_num = 0
    for part in layout:
        part_type = 83  # Default to Linux
        percent = part
        part_num += 1

        if isinstance(part, list):
            if len(part) != 2:
                raise Exception("Partition was incorrectly defined: %s" % part)
            percent, part_type = part

        part_size = int(float(size) * (float(percent) / 100))

        if part_num == last_part_num:
            part_definition.append(",,%s" % part_type)
        else:
            part_definition.append(",%s,%s" % (part_size, part_type))

    sfdisk_definition = "\n".join(part_definition)
    if len(part_definition) > 4:
        raise Exception("Calculated partition definition is too big\n%s" %
                        sfdisk_definition)

    return sfdisk_definition


def get_partition_gpt_layout(size, layout):
    if isinstance(layout, bool):
        return [(None, [0, 0])]

    partition_specs = []
    for partition in layout:
        if isinstance(partition, list):
            if len(partition) != 2:
                raise Exception(
                    "Partition was incorrectly defined: %s" % partition)
            percent, partition_type = partition
        else:
            percent = partition
            partition_type = None

        part_size = int(float(size) * (float(percent) / 100))
        partition_specs.append((partition_type, [0, '+{}'.format(part_size)]))

    # The last partition should use up all remaining space
    partition_specs[-1][-1][-1] = 0
    return partition_specs


def purge_disk_ptable(device):
    # wipe the first and last megabyte of a disk (or file)
    # gpt stores partition table both at front and at end.
    null = '\0'
    start_len = 1024 * 1024
    end_len = 1024 * 1024
    with open(device, "rb+") as fp:
        fp.write(null * (start_len))
        fp.seek(-end_len, os.SEEK_END)
        fp.write(null * end_len)
        fp.flush()

    read_parttbl(device)


def purge_disk(device):
    """
    Remove parition table entries
    """

    # wipe any file systems first
    for d in enumerate_disk(device):
        if d['type'] not in ["disk", "crypt"]:
            wipefs_cmd = [WIPEFS_CMD, "--all", "/dev/%s" % d['name']]
            try:
                LOG.info("Purging filesystem on /dev/%s", d['name'])
                util.subp(wipefs_cmd)
            except Exception:
                raise Exception("Failed FS purge of /dev/%s" % d['name'])

    purge_disk_ptable(device)


def get_partition_layout(table_type, size, layout):
    """
    Call the appropriate function for creating the table
    definition. Returns the table definition

    This is a future proofing function. To add support for
    other layouts, simply add a "get_partition_%s_layout"
    function.
    """
    return get_dyn_func("get_partition_%s_layout", table_type, size, layout)


def read_parttbl(device):
    """
    Use partprobe instead of 'udevadm'. Partprobe is the only
    reliable way to probe the partition table.
    """
    blkdev_cmd = [BLKDEV_CMD, '--rereadpt', device]
    util.udevadm_settle()
    try:
        util.subp(blkdev_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed reading the partition table %s" % e)

    util.udevadm_settle()


def exec_mkpart_mbr(device, layout):
    """
    Break out of mbr partition to allow for future partition
    types, i.e. gpt
    """
    # Create the partitions
    prt_cmd = [SFDISK_CMD, "--Linux", "--unit=S", "--force", device]
    try:
        util.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise Exception("Failed to partition device %s\n%s" % (device, e))

    read_parttbl(device)


def exec_mkpart_gpt(device, layout):
    try:
        util.subp([SGDISK_CMD, '-Z', device])
        for index, (partition_type, (start, end)) in enumerate(layout):
            index += 1
            util.subp([SGDISK_CMD,
                       '-n', '{}:{}:{}'.format(index, start, end), device])
            if partition_type is not None:
                # convert to a 4 char (or more) string right padded with 0
                # 82 -> 8200.  'Linux' -> 'Linux'
                pinput = str(partition_type).ljust(4, "0")
                util.subp(
                    [SGDISK_CMD, '-t', '{}:{}'.format(index, pinput), device])
    except Exception:
        LOG.warning("Failed to partition device %s", device)
        raise

    read_parttbl(device)


def exec_mkpart(table_type, device, layout):
    """
    Fetches the function for creating the table type.
    This allows to dynamically find which function to call.

    Paramaters:
        table_type: type of partition table to use
        device: the device to work on
        layout: layout definition specific to partition table
    """
    return get_dyn_func("exec_mkpart_%s", table_type, device, layout)


def assert_and_settle_device(device):
    """Assert that device exists and settle so it is fully recognized."""
    if not os.path.exists(device):
        util.udevadm_settle()
        if not os.path.exists(device):
            raise RuntimeError("Device %s did not exist and was not created "
                               "with a udevamd settle." % device)

    # Whether or not the device existed above, it is possible that udev
    # events that would populate udev database (for reading by lsdname) have
    # not yet finished. So settle again.
    util.udevadm_settle()


def mkpart(device, definition):
    """
    Creates the partition table.

    Parameters:
        definition: dictionary describing how to create the partition.

            The following are supported values in the dict:
                overwrite: Should the partition table be created regardless
                            of any pre-exisiting data?
                layout: the layout of the partition table
                table_type: Which partition table to use, defaults to MBR
                device: the device to work on.
    """
    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    LOG.debug("Checking values for %s definition", device)
    overwrite = definition.get('overwrite', False)
    layout = definition.get('layout', False)
    table_type = definition.get('table_type', 'mbr')

    # Check if the default device is a partition or not
    LOG.debug("Checking against default devices")

    if (isinstance(layout, bool) and not layout) or not layout:
        LOG.debug("Device is not to be partitioned, skipping")
        return  # Device is not to be partitioned

    # This prevents you from overwriting the device
    LOG.debug("Checking if device %s is a valid device", device)
    if not is_device_valid(device):
        raise Exception(
            'Device {device} is not a disk device!'.format(device=device))

    # Remove the partition table entries
    if isinstance(layout, str) and layout.lower() == "remove":
        LOG.debug("Instructed to remove partition table entries")
        purge_disk(device)
        return

    LOG.debug("Checking if device layout matches")
    if check_partition_layout(table_type, device, layout):
        LOG.debug("Device partitioning layout matches")
        return True

    LOG.debug("Checking if device is safe to partition")
    if not overwrite and (is_disk_used(device) or is_filesystem(device)):
        LOG.debug("Skipping partitioning on configured device %s", device)
        return

    LOG.debug("Checking for device size of %s", device)
    device_size = get_hdd_size(device)

    LOG.debug("Calculating partition layout")
    part_definition = get_partition_layout(table_type, device_size, layout)
    LOG.debug("   Layout is: %s", part_definition)

    LOG.debug("Creating partition table on %s", device)
    exec_mkpart(table_type, device, part_definition)

    LOG.debug("Partition table created for %s", device)


def lookup_force_flag(fs):
    """
    A force flag might be -F or -F, this look it up
    """
    flags = {
        'ext': '-F',
        'btrfs': '-f',
        'xfs': '-f',
        'reiserfs': '-f',
    }

    if 'ext' in fs.lower():
        fs = 'ext'

    if fs.lower() in flags:
        return flags[fs]

    LOG.warning("Force flag for %s is unknown.", fs)
    return ''


def mkfs(fs_cfg):
    """
    Create a file system on the device.

        label: defines the label to use on the device
        fs_cfg: defines how the filesystem is to look
            The following values are required generally:
                device: which device or cloud defined default_device
                filesystem: which file system type
                overwrite: indiscriminately create the file system
                partition: when device does not define a partition,
                            setting this to a number will mean
                            device + partition. When set to 'auto', the
                            first free device or the first device which
                            matches both label and type will be used.

                            'any' means the first filesystem that matches
                            on the device.

            When 'cmd' is provided then no other parameter is required.
    """
    label = fs_cfg.get('label')
    device = fs_cfg.get('device')
    partition = str(fs_cfg.get('partition', 'any'))
    fs_type = fs_cfg.get('filesystem')
    fs_cmd = fs_cfg.get('cmd', [])
    fs_opts = fs_cfg.get('extra_opts', [])
    fs_replace = fs_cfg.get('replace_fs', False)
    overwrite = fs_cfg.get('overwrite', False)

    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    # This allows you to define the default ephemeral or swap
    LOG.debug("Checking %s against default devices", device)

    if not partition or partition.isdigit():
        # Handle manual definition of partition
        if partition.isdigit():
            device = "%s%s" % (device, partition)
            LOG.debug("Manual request of partition %s for %s",
                      partition, device)

        # Check to see if the fs already exists
        LOG.debug("Checking device %s", device)
        check_label, check_fstype, _ = check_fs(device)
        LOG.debug("Device '%s' has check_label='%s' check_fstype=%s",
                  device, check_label, check_fstype)

        if check_label == label and check_fstype == fs_type:
            LOG.debug("Existing file system found at %s", device)

            if not overwrite:
                LOG.debug("Device %s has required file system", device)
                return
            else:
                LOG.warning("Destroying filesystem on %s", device)

        else:
            LOG.debug("Device %s is cleared for formating", device)

    elif partition and str(partition).lower() in ('auto', 'any'):
        # For auto devices, we match if the filesystem does exist
        odevice = device
        LOG.debug("Identifying device to create %s filesytem on", label)

        # any mean pick the first match on the device with matching fs_type
        label_match = True
        if partition.lower() == 'any':
            label_match = False

        device, reuse = find_device_node(device, fs_type=fs_type, label=label,
                                         label_match=label_match,
                                         replace_fs=fs_replace)
        LOG.debug("Automatic device for %s identified as %s", odevice, device)

        if reuse:
            LOG.debug("Found filesystem match, skipping formating.")
            return

        if not reuse and fs_replace and device:
            LOG.debug("Replacing file system on %s as instructed.", device)

        if not device:
            LOG.debug("No device aviable that matches request. "
                      "Skipping fs creation for %s", fs_cfg)
            return
    elif not partition or str(partition).lower() == 'none':
        LOG.debug("Using the raw device to place filesystem %s on", label)

    else:
        LOG.debug("Error in device identification handling.")
        return

    LOG.debug("File system type '%s' with label '%s' will be created on %s",
              fs_type, label, device)

    # Make sure the device is defined
    if not device:
        LOG.warning("Device is not known: %s", device)
        return

    # Check that we can create the FS
    if not (fs_type or fs_cmd):
        raise Exception(
            "No way to create filesystem '{label}'. fs_type or fs_cmd "
            "must be set.".format(label=label))

    # Create the commands
    shell = False
    if fs_cmd:
        fs_cmd = fs_cfg['cmd'] % {
            'label': label,
            'filesystem': fs_type,
            'device': device,
        }
        shell = True

        if overwrite:
            LOG.warning(
                "fs_setup:overwrite ignored because cmd was specified: %s",
                fs_cmd)
        if fs_opts:
            LOG.warning(
                "fs_setup:extra_opts ignored because cmd was specified: %s",
                fs_cmd)
    else:
        # Find the mkfs command
        mkfs_cmd = util.which("mkfs.%s" % fs_type)
        if not mkfs_cmd:
            mkfs_cmd = util.which("mk%s" % fs_type)

        if not mkfs_cmd:
            LOG.warning("Cannot create fstype '%s'.  No mkfs.%s command",
                        fs_type, fs_type)
            return

        fs_cmd = [mkfs_cmd, device]

        if label:
            fs_cmd.extend(["-L", label])

        # File systems that support the -F flag
        if overwrite or device_type(device) == "disk":
            fs_cmd.append(lookup_force_flag(fs_type))

        # Add the extends FS options
        if fs_opts:
            fs_cmd.extend(fs_opts)

    LOG.debug("Creating file system %s on %s", label, device)
    LOG.debug("     Using cmd: %s", str(fs_cmd))
    try:
        util.subp(fs_cmd, shell=shell)
    except Exception as e:
        raise Exception("Failed to exec of '%s':\n%s" % (fs_cmd, e))

# vi: ts=4 expandtab
