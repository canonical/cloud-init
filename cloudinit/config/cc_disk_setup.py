# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Ben Howard <ben.howard@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
from cloudinit.settings import PER_INSTANCE
from cloudinit import util
import logging
import os
import shlex

frequency = PER_INSTANCE

# Define the commands to use
UDEVADM_CMD = util.which('udevadm')
SFDISK_CMD = util.which("sfdisk")
LSBLK_CMD = util.which("lsblk")
BLKID_CMD = util.which("blkid")
BLKDEV_CMD = util.which("blockdev")
WIPEFS_CMD = util.which("wipefs")

LOG = logging.getLogger(__name__)


def handle(_name, cfg, cloud, log, _args):
    """
    See doc/examples/cloud-config_disk-setup.txt for documentation on the
    format.
    """
    disk_setup = cfg.get("disk_setup")
    if isinstance(disk_setup, dict):
        update_disk_setup_devices(disk_setup, cloud.device_name_to_device)
        log.debug("Partitioning disks: %s", str(disk_setup))
        for disk, definition in disk_setup.items():
            if not isinstance(definition, dict):
                log.warn("Invalid disk definition for %s" % disk)
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
                log.warn("Invalid file system definition: %s" % definition)
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
            LOG.warn("entry in disk_setup not a dict: %s", definition)
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

        if part and 'partition' in definition:
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

    lsblk_cmd = [LSBLK_CMD, '--pairs', '--out', 'NAME,TYPE,FSTYPE,LABEL',
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
        d = {'name': None,
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
    except:
        LOG.warn("Query against device %s failed" % name)
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

    LOG.warn("Failed to find device during available device search.")
    return (None, False)


def is_disk_used(device):
    """
    Check if the device is currently used. Returns true if the device
    has either a file system or a partition entry
    is no filesystem found on the disk.
    """

    # If the child count is higher 1, then there are child nodes
    # such as partition or device mapper nodes
    use_count = [x for x in enumerate_disk(device)]
    if len(use_count.splitlines()) > 1:
        return True

    # If we see a file system, then its used
    _, check_fstype, _ = check_fs(device)
    if check_fstype:
        return True

    return False


def get_hdd_size(device):
    """
    Returns the hard disk size.
    This works with any disk type, including GPT.
    """

    size_cmd = [SFDISK_CMD, '--show-size', device]
    size = None
    try:
        size, _err = util.subp(size_cmd)
    except Exception as e:
        raise Exception("Failed to get %s size\n%s" % (device, e))

    return int(size.strip())


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

    if isinstance(layout, bool):
        # if we are using auto partitioning, or "True" be happy
        # if a single partition exists.
        if layout and len(found_layout) >= 1:
            return True
        return False

    else:
        if len(found_layout) != len(layout):
            return False
        else:
            # This just makes sure that the number of requested
            # partitions and the type labels are right
            for x in range(1, len(layout) + 1):
                if isinstance(layout[x - 1], tuple):
                    _, part_type = layout[x]
                    if int(found_layout[x]) != int(part_type):
                        return False
            return True

    return False


def check_partition_layout(table_type, device, layout):
    """
    See if the partition lay out matches.

    This is future a future proofing function. In order
    to add support for other disk layout schemes, add a
    function called check_partition_%s_layout
    """
    return get_dyn_func("check_partition_%s_layout", table_type, device,
                        layout)


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

        part_size = int((float(size) * (float(percent) / 100)) / 1024)

        if part_num == last_part_num:
            part_definition.append(",,%s" % part_type)
        else:
            part_definition.append(",%s,%s" % (part_size, part_type))

    sfdisk_definition = "\n".join(part_definition)
    if len(part_definition) > 4:
        raise Exception("Calculated partition definition is too big\n%s" %
                        sfdisk_definition)

    return sfdisk_definition


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
                LOG.info("Purging filesystem on /dev/%s" % d['name'])
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
    udev_cmd = [UDEVADM_CMD, 'settle']
    try:
        util.subp(udev_cmd)
        util.subp(blkdev_cmd)
        util.subp(udev_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed reading the partition table %s" % e)


def exec_mkpart_mbr(device, layout):
    """
    Break out of mbr partition to allow for future partition
    types, i.e. gpt
    """
    # Create the partitions
    prt_cmd = [SFDISK_CMD, "--Linux", "-uM", device]
    try:
        util.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise Exception("Failed to partition device %s\n%s" % (device, e))

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

    LOG.debug("Checking values for %s definition" % device)
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
        raise Exception("Device %s is not a disk device!", device)

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
        LOG.debug("Skipping partitioning on configured device %s" % device)
        return

    LOG.debug("Checking for device size")
    device_size = get_hdd_size(device)

    LOG.debug("Calculating partition layout")
    part_definition = get_partition_layout(table_type, device_size, layout)
    LOG.debug("   Layout is: %s" % part_definition)

    LOG.debug("Creating partition table on %s", device)
    exec_mkpart(table_type, device, part_definition)

    LOG.debug("Partition table created for %s", device)


def lookup_force_flag(fs):
    """
    A force flag might be -F or -F, this look it up
    """
    flags = {'ext': '-F',
             'btrfs': '-f',
             'xfs': '-f',
             'reiserfs': '-f',
            }

    if 'ext' in fs.lower():
        fs = 'ext'

    if fs.lower() in flags:
        return flags[fs]

    LOG.warn("Force flag for %s is unknown." % fs)
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
        LOG.debug("Device %s has %s %s", device, check_label, check_fstype)

        if check_label == label and check_fstype == fs_type:
            LOG.debug("Existing file system found at %s", device)

            if not overwrite:
                LOG.debug("Device %s has required file system", device)
                return
            else:
                LOG.warn("Destroying filesystem on %s", device)

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
            LOG.debug("Replacing file system on %s as instructed." % device)

        if not device:
            LOG.debug("No device aviable that matches request. "
                      "Skipping fs creation for %s", fs_cfg)
            return
    elif not partition or str(partition).lower() == 'none':
        LOG.debug("Using the raw device to place filesystem %s on" % label)

    else:
        LOG.debug("Error in device identification handling.")
        return

    LOG.debug("File system %s will be created on %s", label, device)

    # Make sure the device is defined
    if not device:
        LOG.warn("Device is not known: %s", device)
        return

    # Check that we can create the FS
    if not (fs_type or fs_cmd):
        raise Exception("No way to create filesystem '%s'. fs_type or fs_cmd "
                        "must be set.", label)

    # Create the commands
    if fs_cmd:
        fs_cmd = fs_cfg['cmd'] % {'label': label,
                                  'filesystem': fs_type,
                                  'device': device,
                                 }
    else:
        # Find the mkfs command
        mkfs_cmd = util.which("mkfs.%s" % fs_type)
        if not mkfs_cmd:
            mkfs_cmd = util.which("mk%s" % fs_type)

        if not mkfs_cmd:
            LOG.warn("Cannot create fstype '%s'.  No mkfs.%s command", fs_type,
                     fs_type)
            return

        fs_cmd = [mkfs_cmd, device]

        if label:
            fs_cmd.extend(["-L", label])

    # File systems that support the -F flag
    if not fs_cmd and (overwrite or device_type(device) == "disk"):
        fs_cmd.append(lookup_force_flag(fs_type))

    # Add the extends FS options
    if fs_opts:
        fs_cmd.extend(fs_opts)

    LOG.debug("Creating file system %s on %s", label, device)
    LOG.debug("     Using cmd: %s", " ".join(fs_cmd))
    try:
        util.subp(fs_cmd)
    except Exception as e:
        raise Exception("Failed to exec of '%s':\n%s" % (fs_cmd, e))
