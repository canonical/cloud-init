# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Disk Setup: Configure partitions and filesystems."""

import logging
import os
import shlex
from pathlib import Path

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

LANG_C_ENV = {"LANG": "C"}
LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_disk_setup",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["disk_setup", "fs_setup"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """
    See doc/examples/cloud-config-disk-setup.txt for documentation on the
    format.
    """
    device_aliases = cfg.get("device_aliases", {})

    def alias_to_device(cand):
        name = device_aliases.get(cand)
        return cloud.device_name_to_device(name or cand) or name

    disk_setup = cfg.get("disk_setup")
    if isinstance(disk_setup, dict):
        update_disk_setup_devices(disk_setup, alias_to_device)
        LOG.debug("Partitioning disks: %s", str(disk_setup))
        for disk, definition in disk_setup.items():
            if not isinstance(definition, dict):
                LOG.warning("Invalid disk definition for %s", disk)
                continue

            try:
                LOG.debug("Creating new partition table/disk")
                util.log_time(
                    logfunc=LOG.debug,
                    msg="Creating partition on %s" % disk,
                    func=mkpart,
                    args=(disk, definition),
                )
            except Exception as e:
                util.logexc(LOG, "Failed partitioning operation\n%s" % e)

    fs_setup = cfg.get("fs_setup")
    if isinstance(fs_setup, list):
        LOG.debug("setting up filesystems: %s", str(fs_setup))
        update_fs_setup_devices(fs_setup, alias_to_device)
        for definition in fs_setup:
            if not isinstance(definition, dict):
                LOG.warning("Invalid file system definition: %s", definition)
                continue

            try:
                LOG.debug("Creating new filesystem.")
                device = definition.get("device")
                util.log_time(
                    logfunc=LOG.debug,
                    msg="Creating fs for %s" % device,
                    func=mkfs,
                    args=(definition,),
                )
            except Exception as e:
                util.logexc(LOG, "Failed during filesystem operation\n%s" % e)


def update_disk_setup_devices(disk_setup, tformer):
    # update 'disk_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for origname in list(disk_setup):
        transformed = tformer(origname)
        if transformed is None or transformed == origname:
            continue
        if transformed in disk_setup:
            LOG.info(
                "Replacing %s in disk_setup for translation of %s",
                origname,
                transformed,
            )
            del disk_setup[transformed]

        disk_setup[transformed] = disk_setup[origname]
        if isinstance(disk_setup[transformed], dict):
            disk_setup[transformed]["_origname"] = origname
        del disk_setup[origname]
        LOG.debug(
            "updated disk_setup device entry '%s' to '%s'",
            origname,
            transformed,
        )


def update_fs_setup_devices(disk_setup, tformer):
    # update 'fs_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for definition in disk_setup:
        if not isinstance(definition, dict):
            LOG.warning("entry in disk_setup not a dict: %s", definition)
            continue

        origname = definition.get("device")

        if origname is None:
            continue

        (dev, part) = util.expand_dotted_devname(origname)

        tformed = tformer(dev)
        if tformed is not None:
            dev = tformed
            LOG.debug(
                "%s is mapped to disk=%s part=%s", origname, tformed, part
            )
            definition["_origname"] = origname
            definition["device"] = tformed

        if part:
            # In origname with <dev>.N, N overrides 'partition' key.
            if "partition" in definition:
                LOG.warning(
                    "Partition '%s' from dotted device name '%s' "
                    "overrides 'partition' key in %s",
                    part,
                    origname,
                    definition,
                )
                definition["_partition"] = definition["partition"]
            definition["partition"] = part


def value_splitter(values, start=None):
    """
    Returns the key/value pairs of output sent as string
    like:  FOO='BAR' HOME='127.0.0.1'
    """
    _values = shlex.split(values)
    if start:
        _values = _values[start:]

    for key, value in [x.split("=") for x in _values]:
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

    lsblk_cmd = [
        "lsblk",
        "--pairs",
        "--output",
        "NAME,TYPE,FSTYPE,LABEL",
        device,
    ]

    if nodeps:
        lsblk_cmd.append("--nodeps")

    info = None
    try:
        info, _err = subp.subp(lsblk_cmd)
    except Exception as e:
        raise RuntimeError(
            "Failed during disk check for %s\n%s" % (device, e)
        ) from e

    parts = [x for x in (info.strip()).splitlines() if len(x.split()) > 0]

    for part in parts:
        d = {
            "name": None,
            "type": None,
            "fstype": None,
            "label": None,
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

    if partition and d_type == "part":
        return True
    elif not partition and d_type == "disk":
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

    blkid_cmd = ["blkid", "-c", "/dev/null", device]
    try:
        out, _err = subp.subp(blkid_cmd, rcs=[0, 2])
    except Exception as e:
        raise RuntimeError(
            "Failed during disk check for %s\n%s" % (device, e)
        ) from e

    if out:
        if len(out.splitlines()) == 1:
            for key, value in value_splitter(out, start=1):
                if key.lower() == "label":
                    label = value
                elif key.lower() == "type":
                    fs_type = value
                elif key.lower() == "uuid":
                    uuid = value

    return label, fs_type, uuid


def is_filesystem(device):
    """
    Returns true if the device has a file system.
    """
    _, fs_type, _ = check_fs(device)
    return fs_type


def find_device_node(
    device,
    fs_type=None,
    label=None,
    valid_targets=None,
    label_match=True,
    replace_fs=None,
):
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
        valid_targets = ["disk", "part"]

    raw_device_used = False
    for d in enumerate_disk(device):

        if d["fstype"] == replace_fs and label_match is False:
            # We found a device where we want to replace the FS
            return ("/dev/%s" % d["name"], False)

        if d["fstype"] == fs_type and (
            (label_match and d["label"] == label) or not label_match
        ):
            # If we find a matching device, we return that
            return ("/dev/%s" % d["name"], True)

        if d["type"] in valid_targets:

            if d["type"] != "disk" or d["fstype"]:
                raw_device_used = True

            if d["type"] == "disk":
                # Skip the raw disk, its the default
                pass

            elif not d["fstype"]:
                return ("/dev/%s" % d["name"], False)

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


def get_hdd_size(device):
    try:
        size_in_bytes, _ = subp.subp(["blockdev", "--getsize64", device])
        sector_size, _ = subp.subp(["blockdev", "--getss", device])
    except Exception as e:
        raise RuntimeError("Failed to get %s size\n%s" % (device, e)) from e

    return int(size_in_bytes) / int(sector_size)


def check_partition_mbr_layout(device, layout):
    """
    Returns true if the partition layout matches the one on the disk

    Layout should be a list of values. At this time, this only
    verifies that the number of partitions and their labels is correct.
    """

    read_parttbl(device)

    prt_cmd = ["sfdisk", "-l", device]
    try:
        out, _err = subp.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise RuntimeError(
            "Error running partition command on %s\n%s" % (device, e)
        ) from e

    found_layout = []
    for line in out.splitlines():
        _line = line.split()
        if len(_line) == 0:
            continue

        if device in _line[0]:
            # We don't understand extended partitions yet
            if _line[-1].lower() in ["extended", "empty"]:
                continue

            # Find the partition types
            type_label = None
            for x in sorted(range(1, len(_line)), reverse=True):
                if _line[x].isdigit() and _line[x] != "/":
                    type_label = _line[x]
                    break

            found_layout.append(type_label)
    return found_layout


def check_partition_gpt_layout(device, layout):
    prt_cmd = ["sgdisk", "-p", device]
    try:
        out, _err = subp.subp(prt_cmd, update_env=LANG_C_ENV)
    except Exception as e:
        raise RuntimeError(
            "Error running partition command on %s\n%s" % (device, e)
        ) from e

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
        if line.strip().startswith("Number"):
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
    if "gpt" == table_type:
        found_layout = check_partition_gpt_layout(device, layout)
    elif "mbr" == table_type:
        found_layout = check_partition_mbr_layout(device, layout)
    else:
        raise RuntimeError("Unable to determine table type")

    LOG.debug(
        "called check_partition_%s_layout(%s, %s), returned: %s",
        table_type,
        device,
        layout,
        found_layout,
    )
    if isinstance(layout, bool):
        # if we are using auto partitioning, or "True" be happy
        # if a single partition exists.
        if layout and len(found_layout) >= 1:
            return True
        return False

    elif len(found_layout) == len(layout):
        # This just makes sure that the number of requested
        # partitions and the type labels are right
        layout_types = [
            str(x[1]) if isinstance(x, (tuple, list)) else None for x in layout
        ]
        LOG.debug(
            "Layout types=%s. Found types=%s", layout_types, found_layout
        )
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
        # Create a single partition, default to Linux
        return ",,83"

    if (len(layout) == 0 and isinstance(layout, list)) or not isinstance(
        layout, list
    ):
        raise RuntimeError("Partition layout is invalid")

    last_part_num = len(layout)
    if last_part_num > 4:
        raise RuntimeError("Only simply partitioning is allowed.")

    part_definition = []
    part_num = 0
    for part in layout:
        part_type = 83  # Default to Linux
        percent = part
        part_num += 1

        if isinstance(part, list):
            if len(part) != 2:
                raise RuntimeError(
                    "Partition was incorrectly defined: %s" % part
                )
            percent, part_type = part

        part_size = int(float(size) * (float(percent) / 100))

        if part_num == last_part_num:
            part_definition.append(",,%s" % part_type)
        else:
            part_definition.append(",%s,%s" % (part_size, part_type))

    sfdisk_definition = "\n".join(part_definition)
    if len(part_definition) > 4:
        raise RuntimeError(
            "Calculated partition definition is too big\n%s"
            % sfdisk_definition
        )

    return sfdisk_definition


def get_partition_gpt_layout(size, layout):
    if isinstance(layout, bool):
        return [(None, [0, 0])]

    partition_specs = []
    for partition in layout:
        if isinstance(partition, list):
            if len(partition) != 2:
                raise RuntimeError(
                    "Partition was incorrectly defined: %s" % partition
                )
            percent, partition_type = partition
        else:
            percent = partition
            partition_type = None

        part_size = int(float(size) * (float(percent) / 100))
        partition_specs.append((partition_type, [0, "+{}".format(part_size)]))

    # The last partition should use up all remaining space
    partition_specs[-1][-1][-1] = 0
    return partition_specs


def purge_disk_ptable(device):
    # wipe the first and last megabyte of a disk (or file)
    # gpt stores partition table both at front and at end.
    null = b"\0"
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
    Remove partition table entries
    """

    # wipe any file systems first
    for d in enumerate_disk(device):
        if d["type"] not in ["disk", "crypt"]:
            wipefs_cmd = ["wipefs", "--all", "/dev/%s" % d["name"]]
            try:
                LOG.info("Purging filesystem on /dev/%s", d["name"])
                subp.subp(wipefs_cmd)
            except Exception as e:
                raise RuntimeError(
                    "Failed FS purge of /dev/%s" % d["name"]
                ) from e

    purge_disk_ptable(device)


def get_partition_layout(table_type, size, layout):
    """
    Call the appropriate function for creating the table
    definition. Returns the table definition

    This is a future proofing function. To add support for
    other layouts, simply add a "get_partition_%s_layout"
    function.
    """
    if "mbr" == table_type:
        return get_partition_mbr_layout(size, layout)
    elif "gpt" == table_type:
        return get_partition_gpt_layout(size, layout)
    raise RuntimeError("Unable to determine table type")


def read_parttbl(device):
    """
    `Partprobe` is preferred over `blkdev` since it is more reliably
    able to probe the partition table.
    """
    partprobe = "partprobe"
    if subp.which(partprobe):
        probe_cmd = [partprobe, device]
    else:
        probe_cmd = ["blockdev", "--rereadpt", device]
    util.udevadm_settle()
    try:
        subp.subp(probe_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed reading the partition table %s" % e)

    util.udevadm_settle()


def exec_mkpart_mbr(device, layout):
    """
    Break out of mbr partition to allow for future partition
    types, i.e. gpt
    """
    # Create the partitions
    prt_cmd = ["sfdisk", "--force", device]
    try:
        subp.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise RuntimeError(
            "Failed to partition device %s\n%s" % (device, e)
        ) from e

    read_parttbl(device)


def exec_mkpart_gpt(device, layout):
    try:
        subp.subp(["sgdisk", "-Z", device])
        for index, (partition_type, (start, end)) in enumerate(layout):
            index += 1
            subp.subp(
                [
                    "sgdisk",
                    "-n",
                    "{}:{}:{}".format(index, start, end),
                    device,
                ]
            )
            if partition_type is not None:
                # convert to a 4 char (or more) string right padded with 0
                # 82 -> 8200.  'Linux' -> 'Linux'
                pinput = str(partition_type).ljust(4, "0")
                subp.subp(
                    ["sgdisk", "-t", "{}:{}".format(index, pinput), device]
                )
    except Exception:
        LOG.warning("Failed to partition device %s", device)
        raise

    read_parttbl(device)


def assert_and_settle_device(device):
    """Assert that device exists and settle so it is fully recognized."""
    if not os.path.exists(device):
        util.udevadm_settle()
        if not os.path.exists(device):
            raise RuntimeError(
                "Device %s did not exist and was not created "
                "with a udevadm settle." % device
            )

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
                            of any pre-existing data?
                layout: the layout of the partition table
                table_type: Which partition table to use, defaults to MBR
                device: the device to work on.
    """
    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    LOG.debug("Checking values for %s definition", device)
    overwrite = definition.get("overwrite", False)
    layout = definition.get("layout", False)
    table_type = definition.get("table_type", "mbr")

    # Check if the default device is a partition or not
    LOG.debug("Checking against default devices")

    if (isinstance(layout, bool) and not layout) or not layout:
        LOG.debug("Device is not to be partitioned, skipping")
        return  # Device is not to be partitioned

    # This prevents you from overwriting the device
    LOG.debug("Checking if device %s is a valid device", device)
    if not is_device_valid(device):
        raise RuntimeError(
            "Device {device} is not a disk device!".format(device=device)
        )

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
    if "mbr" == table_type:
        exec_mkpart_mbr(device, part_definition)
    elif "gpt" == table_type:
        exec_mkpart_gpt(device, part_definition)
    else:
        raise RuntimeError("Unable to determine table type")

    LOG.debug("Partition table created for %s", device)


def lookup_force_flag(fs):
    """
    A force flag might be -F or -F, this look it up
    """
    flags = {
        "ext": "-F",
        "btrfs": "-f",
        "xfs": "-f",
        "reiserfs": "-f",
        "swap": "-f",
    }

    if "ext" in fs.lower():
        fs = "ext"

    if fs.lower() in flags:
        return flags[fs]

    LOG.warning("Force flag for %s is unknown.", fs)
    return ""


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
    label = fs_cfg.get("label")
    device = fs_cfg.get("device")
    partition = str(fs_cfg.get("partition", "any"))
    fs_type = fs_cfg.get("filesystem")
    fs_cmd = fs_cfg.get("cmd", [])
    fs_opts = fs_cfg.get("extra_opts", [])
    fs_replace = fs_cfg.get("replace_fs", False)
    overwrite = fs_cfg.get("overwrite", False)

    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    # This allows you to define the default ephemeral or swap
    LOG.debug("Checking %s against default devices", device)

    if not partition or partition.isdigit():
        # Handle manual definition of partition
        if partition.isdigit():
            # nvme support
            # https://github.com/torvalds/linux/blob/45db3ab/block/partitions
            # /core.c#L330
            if device[-1].isdigit():
                device = f"{device}p"
            device = "%s%s" % (device, partition)
            if not Path(device).is_block_device():
                LOG.warning("Path %s does not exist or is not a block device")
                return
            LOG.debug(
                "Manual request of partition %s for %s", partition, device
            )

        # Check to see if the fs already exists
        LOG.debug("Checking device %s", device)
        check_label, check_fstype, _ = check_fs(device)
        LOG.debug(
            "Device '%s' has check_label='%s' check_fstype=%s",
            device,
            check_label,
            check_fstype,
        )

        if check_label == label and check_fstype == fs_type:
            LOG.debug("Existing file system found at %s", device)

            if not overwrite:
                LOG.debug("Device %s has required file system", device)
                return
            else:
                LOG.debug("Destroying filesystem on %s", device)

        else:
            LOG.debug("Device %s is cleared for formatting", device)

    elif partition and str(partition).lower() in ("auto", "any"):
        # For auto devices, we match if the filesystem does exist
        odevice = device
        LOG.debug("Identifying device to create %s filesystem on", label)

        # 'any' means pick the first match on the device with matching fs_type
        label_match = True
        if partition.lower() == "any":
            label_match = False

        device, reuse = find_device_node(
            device,
            fs_type=fs_type,
            label=label,
            label_match=label_match,
            replace_fs=fs_replace,
        )
        LOG.debug("Automatic device for %s identified as %s", odevice, device)

        if reuse:
            LOG.debug("Found filesystem match, skipping formatting.")
            return

        if not reuse and fs_replace and device:
            LOG.debug("Replacing file system on %s as instructed.", device)

        if not device:
            LOG.debug(
                "No device available that matches request. "
                "Skipping fs creation for %s",
                fs_cfg,
            )
            return
    elif not partition or str(partition).lower() == "none":
        LOG.debug("Using the raw device to place filesystem %s on", label)

    else:
        LOG.debug("Error in device identification handling.")
        return

    LOG.debug(
        "File system type '%s' with label '%s' will be created on %s",
        fs_type,
        label,
        device,
    )

    # Make sure the device is defined
    if not device:
        LOG.warning("Device is not known: %s", device)
        return

    # Check that we can create the FS
    if not (fs_type or fs_cmd):
        raise RuntimeError(
            "No way to create filesystem '{label}'. fs_type or fs_cmd "
            "must be set.".format(label=label)
        )

    # Create the commands
    shell = False
    if fs_cmd:
        fs_cmd = fs_cfg["cmd"] % {
            "label": label,
            "filesystem": fs_type,
            "device": device,
        }
        shell = True

        if overwrite:
            LOG.warning(
                "fs_setup:overwrite ignored because cmd was specified: %s",
                fs_cmd,
            )
        if fs_opts:
            LOG.warning(
                "fs_setup:extra_opts ignored because cmd was specified: %s",
                fs_cmd,
            )
    else:
        # Find the mkfs command
        mkfs_cmd = subp.which("mkfs.%s" % fs_type)
        if not mkfs_cmd:
            # for "mkswap"
            mkfs_cmd = subp.which("mk%s" % fs_type)

        if not mkfs_cmd:
            LOG.warning(
                "Cannot create fstype '%s'.  No mkfs.%s command",
                fs_type,
                fs_type,
            )
            return

        fs_cmd = [mkfs_cmd]

        if label:
            fs_cmd.extend(["-L", label])

        # File systems that support the -F flag
        if overwrite or device_type(device) == "disk":
            force_flag = lookup_force_flag(fs_type)
            if force_flag:
                fs_cmd.append(force_flag)

        # Add the extends FS options
        if fs_opts:
            fs_cmd.extend(fs_opts)

        fs_cmd.append(device)

    LOG.debug("Creating file system %s on %s", label, device)
    LOG.debug("     Using cmd: %s", str(fs_cmd))
    try:
        subp.subp(fs_cmd, shell=shell)
    except Exception as e:
        raise RuntimeError("Failed to exec of '%s':\n%s" % (fs_cmd, e)) from e
