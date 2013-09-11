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
from cloudinit import util
from cloudinit.settings import PER_INSTANCE
import re
import traceback

frequency = PER_INSTANCE

virtal_devices = ["ephemeral0", "swap"]
defmnts = ["ephemeral0", "swap"]

# Define the commands to use
UDEVADM_CMD = util.which('udevadm')
SFDISK_CMD = util.which("sfdisk")
LSBLK_CMD = util.which("lsblk")
BLKID_CMD = util.which("blkid")
BLKDEV_CMD = util.which("blockdev")

def handle(_name, cfg, cloud, log, _args):
    """
    Call util.prep_disk for disk_setup cloud-config.
    The format is:

    disk_setup:
        ephmeral0: {type='mbr', layout='True', overwrite='False'}
        /dev/xvdj: {type='None'}
        /dev/xvdh: {type='mbr', layout:[(33,83),66], overwrite='True'}

    fs_setup:
        ephemeral0: {filesystem='ext3', device='ephemeral0', partition='auto'}
        mylabel2: {filesystem='ext3', device='/dev/xvda1', partition='None'}
        special1: {cmd="mkfs -t %(FILESYSTEM)s -L %(LABEL)s %(DEVICE)s", filesystem='btrfs', device='/dev/xvda1'}


    """

    disk_setup = cfg.get("disk_setup")
    if isinstance(disk_setup, dict):
        log.info("Partitioning disks.")
        for disk, definition in disk_setup.items():
            if not isinstance(definition, dict):
                log.debug("Invalid disk definition for %s" % disk)
                continue

            util.log_time(logfunc=log.info,
                              msg="Creating partition on %s" % disk,
                              func=mkpart, args=(disk, cloud, definition, log))

    fs_setup = cfg.get("fs_setup")
    if isinstance(fs_setup, dict):
        log.info("Setting up filesystems")
        for label, definition in fs_setup.items():
            if not isinstance(definition, dict):
               log.debug("Invalid filesystem definition for %s" % label)
               continue

            util.log_time(logfunc=log.debug, msg="Creating fs for %s" % label,
                         func=mkfs, args=(label, cloud, definition, log))


def is_default_device(name, cloud, fallback=None):
    """
    Ask the cloud datasource if the 'name' maps to a default
    device. If so, return that value, otherwise return 'name', or
    fallback if so defined.
    """

    try:
        _dev = cloud.device_name_to_device(name)
    except Exception as e:
        print e

    if _dev:
        return _dev

    if fallback:
        return fallback

    return name


def check_value(key, dct, default=None):
    """
    Convience function for getting value out of a dict.
    """

    if key in dct:
        return dct[key]
    if default:
        return default
    return None


def value_splitter(values, start=None):
    """
    Returns the key/value pairs of output sent as string
    like:  FOO='BAR' HOME='127.0.0.1'
    """
    _values = values.split()
    if start:
        _values = _values[start:]

    for key, value in [x.split('=') for x in _values]:
        if value == '""':
            value = None
        elif '"' in value:
            value = value.replace('"','')
        yield key, value

def device_type(device):
    """
    Return the device type of the device by calling lsblk.
    """

    lsblk_cmd = [LSBLK_CMD, '--pairs', '--nodeps', '--out', 'NAME,TYPE',
                 device]
    info = None
    try:
        info, _err = util.subp(lsblk_cmd)
    except Exception as e:
        raise Exception("Failed during disk check for %s\n%s" % (device, e))

    for key, value in value_splitter(info):
        if key.lower() == "type":
            return value.lower()

    return None


def is_device_valid(name, partition=False):
    """
    Check if the device is a valid device.
    """
    d_type = device_type(name)
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
        util.logexc(e)
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


def find_device_node(device, fs_type=None, label=None, valid_targets=None):
    """
    Find a device that is either matches the spec, or the first

    The return is value is (<device>, <bool>) where the device is the
    device to use and the bool is whether the device matches the
    fs_type and label.

    Note: This works with GPT partition tables!
    """
    if not valid_targets:
        valid_targets = ['disk', 'part']

    lsblk_cmd = [LSBLK_CMD, '--pairs', '--out', 'NAME,TYPE,FSTYPE,LABEL', device]
    info = None
    try:
        info, _err = util.subp(lsblk_cmd)
    except Exception as e:
        raise Exception("Failed during disk check for %s\n%s" % (device, e))

    raw_device_used = False
    parts = [ x for x in (info.strip()).splitlines() if len(x.split()) > 0 ]

    for part in parts:
        d = {'name': None,
             'type': None,
             'fstype': None,
             'label': None,
            }

        for key, value in value_splitter(part):
            d[key.lower()] = value

        if d['fstype'] == fs_type and d['label'] == label:
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

    return (None, False)


def is_disk_used(device):
    """
    Check if the device is currently used. Returns false if there
    is no filesystem found on the disk.
    """
    lsblk_cmd = [LSBLK_CMD, '--pairs', '--out', 'NAME,TYPE',
                 device]
    info = None
    try:
        info, _err = util.subp(lsblk_cmd)
    except Exception as e:
        # if we error out, we can't use the device
        return True

    # If there is any output, then the device has something
    if len(info.splitlines()) > 1:
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
                if isinstance(layout[x-1], tuple):
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

    if (len(layout) == 0 and isinstance(layout, list)) or \
        not isinstance(layout, list):
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
                raise Exception("Partition was incorrectly defined: %s" % \
                                part)
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
    try:
        util.subp(blkdev_cmd)
    except Exception as e:
        raise Exception("Failed on call to partprobe\n%s" % e)


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


def mkpart(device, cloud, definition, log):
    """
    Creates the partition table.

    Parameters:
        cloud: the cloud object
        definition: dictionary describing how to create the partition.

            The following are supported values in the dict:
                overwrite: Should the partition table be created regardless
                            of any pre-exisiting data?
                layout: the layout of the partition table
                table_type: Which partition table to use, defaults to MBR
                device: the device to work on.
    """

    log.debug("Checking values for %s definition" % device)
    overwrite = check_value('overwrite', definition, False)
    layout = check_value('layout', definition, False)
    table_type = check_value('type', definition, 'mbr')
    _device = is_default_device(device, cloud)

    # Check if the default device is a partition or not
    log.debug("Checking against default devices")
    if _device and (_device != device):
        if not is_device_valid(_device):
            _device = _device[:-1]

        if not is_device_valid(_device):
            raise Exception("Unable to find backing block device for %s" % \
                            device)

    if (isinstance(layout, bool) and not layout) or not layout:
        log.debug("Device is not to be partitioned, skipping")
        return  # Device is not to be partitioned

    # This prevents you from overwriting the device
    log.debug("Checking if device %s is a valid device" % device)
    if not is_device_valid(device):
        raise Exception("Device %s is not a disk device!" % device)

    log.debug("Checking if device layout matches")
    if check_partition_layout(table_type, device, layout):
        log.debug("Device partitioning layout matches")
        return True

    log.debug("Checking if device is safe to partition")
    if not overwrite and (is_disk_used(device) or is_filesystem(device)):
        log.debug("Skipping partitioning on configured device %s" % device)
        return

    log.debug("Checking for device size")
    device_size = get_hdd_size(device)

    log.debug("Calculating partition layout")
    part_definition = get_partition_layout(table_type, device_size, layout)
    log.debug("   Layout is: %s" % part_definition)

    log.debug("Creating partition table on %s" % device)
    exec_mkpart(table_type, device, part_definition)

    log.debug("Partition table created for %s" % device)


def mkfs(label, cloud, fs_cfg, log):
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

            When 'cmd' is provided then no other parameter is required.
    """
    device = check_value('device', fs_cfg)
    partition = str(check_value('partition', fs_cfg))
    fs_type = check_value('filesystem', fs_cfg)
    fs_cmd = check_value('cmd', fs_cfg, [])
    fs_opts = check_value('extra_opts', fs_cfg, [])
    overwrite = check_value('overwrite', fs_cfg, False)

    # This allows you to define the default ephemeral or swap
    log.debug("Checking %s label against default devices" % label)
    device = is_default_device(label, cloud, fallback=device)

    if not partition or partition.isdigit():
        # Handle manual definition of partition
        if partition.isdigit():
            device = "%s%s" % (device, partition)
            log.debug("Manual request of partition %s for %s" % (
                         partition, device))

        # Check to see if the fs already exists
        log.debug("Checking device %s" % device)
        check_label, check_fstype, _ = check_fs(device)
        log.debug("Device %s has %s %s" % (device, check_label, check_fstype))

        if check_label == label and check_fstype == fs_type:
            log.debug("Existing file system found at %s" % device)

            if not overwrite:
                log.debug("Device %s has required file system" % device)
                return
            else:
                log.debug("Destroying filesystem on %s" % device)

        else:
            log.debug("Device %s is cleared for formating" % device)

    elif partition and partition == 'auto':
        # For auto devices, we match if the filesystem does exist
        log.debug("Identifying device to create %s filesytem on" % label)
        device, reuse = find_device_node(device, fs_type=fs_type, label=label)
        log.debug("Device identified as %s" % device)

        if reuse:
            log.debug("Found filesystem match, skipping formating.")
            return

    else:
        log.debug("Error in device identification handling.")
        return


    log.debug("File system %s will be created on %s" % (label, device))

    # Make sure the device is defined
    if not device:
        raise Exception("Device identification error for %s" % label)

    # Check that we can create the FS
    if not label or not fs_type:
        log.debug("Command to create filesystem %s is bad. Skipping." % \
                     label)

    # Create the commands
    if fs_cmd:
        fs_cmd = fs_cfg['cmd'] % {'label': label,
                                  'filesystem': fs_type,
                                  'device': device,
                                 }
    else:
        mkfs_cmd = util.which("mkfs.%s" % fs_type)
        if not mkfs_cmd:
            mkfs_cmd = util.which("mk%s" % fs_type)

        if not mkfs_cmd:
            log.debug("Unable to locate command to create filesystem.")
            return

        fs_cmd = [mkfs_cmd, "-L", label, device]

    # Add the extends FS options
    if fs_opts:
        fs_cmd.extend(fs_opts)

    log.debug("Creating file system %s on %s" % (label, device))
    print fs_cmd
    try:
        util.subp(fs_cmd)
    except Exception as e:
        raise Exception("Failed to exec of '%s':\n%s" % (fs_cmd, e))
