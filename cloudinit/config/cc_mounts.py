# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Mounts: Configure mount points and swap files"""


import copy
import logging
import math
import os
import re
from typing import Dict, List, Optional, Tuple, cast

from cloudinit import performance, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_mounts",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}

# Shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1, sr0
DEVICE_NAME_FILTER = r"^([x]{0,1}[shv]d[a-z][0-9]*|sr[0-9]+)$"
# Name matches 'server:/path'
NETWORK_NAME_FILTER = r"^.+:.*"
FSTAB_PATH = "/etc/fstab"
MNT_COMMENT = "comment=cloudconfig"
MB = 2**20
GB = 2**30

LOG = logging.getLogger(__name__)


def is_meta_device_name(name):
    # return true if this is a metadata service name
    if name in ["ami", "root", "swap"]:
        return True
    # names 'ephemeral0' or 'ephemeral1'
    # 'ebs[0-9]' appears when '--block-device-mapping sdf=snap-d4d90bbc'
    for enumname in ("ephemeral", "ebs"):
        if name.startswith(enumname) and name.find(":") == -1:
            return True
    return False


def is_network_device(name):
    # return true if this is a network device
    if re.match(NETWORK_NAME_FILTER, name):
        return True
    return False


def _get_nth_partition_for_device(device_path, partition_number):
    potential_suffixes = [
        str(partition_number),
        "p%s" % (partition_number,),
        "-part%s" % (partition_number,),
    ]
    for suffix in potential_suffixes:
        potential_partition_device = "%s%s" % (device_path, suffix)
        if os.path.exists(potential_partition_device):
            return potential_partition_device
    return None


def _is_block_device(device_path, partition_path=None):
    device_name = os.path.realpath(device_path).split("/")[-1]
    sys_path = os.path.join("/sys/block/", device_name)
    if partition_path is not None:
        sys_path = os.path.join(
            sys_path, os.path.realpath(partition_path).split("/")[-1]
        )
    return os.path.exists(sys_path)


def sanitize_devname(startname, transformer, aliases=None):
    LOG.debug("Attempting to determine the real name of %s", startname)

    # workaround, allow user to specify 'ephemeral'
    # rather than more ec2 correct 'ephemeral0'
    devname = startname
    if devname == "ephemeral":
        devname = "ephemeral0"
        LOG.debug("Adjusted mount option from ephemeral to ephemeral0")

    if is_network_device(startname):
        return startname

    device_path, partition_number = util.expand_dotted_devname(devname)
    orig = device_path

    if aliases:
        device_path = aliases.get(device_path, device_path)
        if orig != device_path:
            LOG.debug("Mapped device alias %s to %s", orig, device_path)

    if is_meta_device_name(device_path):
        device_path = transformer(device_path)
        if not device_path:
            return None
        if not device_path.startswith("/"):
            device_path = "/dev/%s" % (device_path,)
        LOG.debug("Mapped metadata name %s to %s", orig, device_path)
    else:
        if re.match(DEVICE_NAME_FILTER, startname):
            device_path = "/dev/%s" % (device_path,)

    partition_path = None
    if partition_number is None:
        partition_path = _get_nth_partition_for_device(device_path, 1)
    else:
        partition_path = _get_nth_partition_for_device(
            device_path, partition_number
        )
        if partition_path is None:
            return None

    if _is_block_device(device_path, partition_path):
        if partition_path is not None:
            return partition_path
        return device_path
    return None


def sanitized_devname_is_valid(
    original: str, sanitized: Optional[str], fstab_devs: Dict[str, str]
) -> bool:
    """Get if the sanitized device name is valid."""
    if sanitized != original:
        LOG.debug("changed %s => %s", original, sanitized)
    if sanitized is None:
        LOG.debug("Ignoring nonexistent default named mount %s", original)
        return False
    elif sanitized in fstab_devs:
        LOG.debug(
            "Device %s already defined in fstab: %s",
            sanitized,
            fstab_devs[sanitized],
        )
        return False
    return True


def suggested_swapsize(memsize=None, maxsize=None, fsys=None):
    # make a suggestion on the size of swap for this system.
    if memsize is None:
        memsize = util.read_meminfo()["total"]

    sugg_max = memsize * 2

    info = {"avail": "na", "max_in": maxsize, "mem": memsize}

    if fsys is None and maxsize is None:
        # set max to default if no filesystem given
        maxsize = sugg_max
    elif fsys:
        statvfs = os.statvfs(fsys)
        avail = statvfs.f_frsize * statvfs.f_bfree
        info["avail"] = avail

        if maxsize is None:
            # set to 25% of filesystem space
            maxsize = min(int(avail / 4), sugg_max)
        elif maxsize > ((avail * 0.9)):
            # set to 90% of available disk space
            maxsize = int(avail * 0.9)
    elif maxsize is None:
        maxsize = sugg_max

    info["max"] = maxsize

    if memsize < 4 * GB:
        minsize = memsize
    elif memsize < 16 * GB:
        minsize = 4 * GB
    else:
        minsize = round(math.sqrt(memsize / GB)) * GB

    size = min(minsize, maxsize)

    info["size"] = size

    pinfo = {}
    for k, v in info.items():
        if isinstance(v, int):
            pinfo[k] = "%s MB" % (v / MB)
        else:
            pinfo[k] = v

    LOG.debug(
        "suggest %s swap for %s memory with '%s' disk given max=%s [max=%s]'",
        pinfo["size"],
        pinfo["mem"],
        pinfo["avail"],
        pinfo["max_in"],
        pinfo["max"],
    )
    return size


def create_swapfile(fname: str, size: str) -> None:
    """Size is in MiB."""

    errmsg = "Failed to create swapfile '%s' of size %sMB via %s: %s"

    def create_swap(fname, size, method):
        LOG.debug(
            "Creating swapfile in '%s' on fstype '%s' using '%s'",
            fname,
            fstype,
            method,
        )

        if method == "fallocate":
            cmd = ["fallocate", "-l", "%sM" % size, fname]
        elif method == "dd":
            cmd = [
                "dd",
                "if=/dev/zero",
                "of=%s" % fname,
                "bs=1M",
                "count=%s" % size,
            ]
        else:
            raise subp.ProcessExecutionError(
                "Missing dependency: 'dd' and 'fallocate' are not available"
            )

        try:
            subp.subp(cmd, capture=True)
        except subp.ProcessExecutionError as e:
            LOG.info(errmsg, fname, size, method, e)
            util.del_file(fname)
            raise

    swap_dir = os.path.dirname(fname)
    util.ensure_dir(swap_dir)

    fstype = util.get_mount_info(swap_dir)[1]

    if fstype == "btrfs":
        subp.subp(["truncate", "-s", "0", fname])
        subp.subp(["chattr", "+C", fname])

    if fstype == "xfs" and util.kernel_version() < (4, 18):
        create_swap(fname, size, "dd")
    else:
        try:
            create_swap(fname, size, "fallocate")
        except subp.ProcessExecutionError:
            LOG.info("fallocate swap creation failed, will attempt with dd")
            create_swap(fname, size, "dd")

    if os.path.exists(fname):
        util.chmod(fname, 0o600)
    try:
        subp.subp(["mkswap", fname])
    except subp.ProcessExecutionError:
        util.del_file(fname)
        raise


def setup_swapfile(fname, size=None, maxsize=None):
    """
    fname: full path string of filename to setup
    size: the size to create. set to "auto" for recommended
    maxsize: the maximum size
    """
    swap_dir = os.path.dirname(fname)
    if str(size).lower() == "auto":
        try:
            memsize = util.read_meminfo()["total"]
        except IOError:
            LOG.debug("Not creating swap: failed to read meminfo")
            return

        util.ensure_dir(swap_dir)
        size = suggested_swapsize(
            fsys=swap_dir, maxsize=maxsize, memsize=memsize
        )

    mibsize = str(int(size / (2**20)))
    if not size:
        LOG.debug("Not creating swap: suggested size was 0")
        return

    with performance.Timed("Setting up swap file"):
        create_swapfile(fname, mibsize)

    return fname


def handle_swapcfg(swapcfg):
    """handle the swap config, calling setup_swap if necessary.
    return None or (filename, size)
    """
    if not isinstance(swapcfg, dict):
        LOG.warning("input for swap config was not a dict.")
        return None

    fname = swapcfg.get("filename", "/swap.img")
    size = swapcfg.get("size", 0)
    maxsize = swapcfg.get("maxsize", None)

    if not (size and fname):
        LOG.debug("no need to setup swap")
        return

    if os.path.exists(fname):
        if not os.path.exists("/proc/swaps"):
            LOG.debug(
                "swap file %s exists, but no /proc/swaps exists, being safe",
                fname,
            )
            return fname
        try:
            for line in util.load_text_file("/proc/swaps").splitlines():
                if line.startswith(fname + " "):
                    LOG.debug("swap file %s already in use", fname)
                    return fname
            LOG.debug("swap file %s exists, but not in /proc/swaps", fname)
        except Exception:
            LOG.warning(
                "swap file %s exists. Error reading /proc/swaps", fname
            )
            return fname

    try:
        if isinstance(size, str) and size != "auto":
            size = util.human2bytes(size)
        if isinstance(maxsize, str):
            maxsize = util.human2bytes(maxsize)
        return setup_swapfile(fname=fname, size=size, maxsize=maxsize)

    except Exception as e:
        LOG.warning("failed to setup swap: %s", e)

    return None


def parse_fstab() -> Tuple[List[str], Dict[str, str], List[str]]:
    """Parse /etc/fstab.

    Parse fstab, ignoring any lines containing "comment=cloudconfig".
    :return: A 3-tuple containing:
        - A list of lines exactly as they appear in fstab
        - A dictionary with key being the first token in the line
          and value being the entire line
        - A list of any lines that were ignored due to "comment=cloudconfig"
    """
    fstab_lines = []
    fstab_devs = {}
    fstab_removed = []

    if os.path.exists(FSTAB_PATH):
        for line in util.load_text_file(FSTAB_PATH).splitlines():
            if MNT_COMMENT in line:
                fstab_removed.append(line)
                continue
            toks = line.split()
            if toks:
                fstab_devs[toks[0]] = line
                fstab_lines.append(line)
    return fstab_lines, fstab_devs, fstab_removed


def sanitize_mounts_configuration(
    mounts: List[Optional[List[Optional[str]]]],
    fstab_devs: Dict[str, str],
    device_aliases: Dict[str, str],
    default_fields: List[Optional[str]],
    cloud: Cloud,
) -> List[List[str]]:
    """Sanitize mounts to ensure we can work with devices in config.

    Specifically:
     - Ensure the mounts configuration is a list of lists
     - Transform and sanitize device names
     - Ensure all tokens are strings
     - Add default options to any lines without options
    """
    updated_lines = []
    for line in mounts:
        # skip something that wasn't a list
        if not isinstance(line, list):
            LOG.warning("Mount option not a list, ignoring: %s", line)
            continue

        start = str(line[0])
        sanitized_devname = sanitize_devname(
            start, cloud.device_name_to_device, aliases=device_aliases
        )
        if sanitized_devname_is_valid(start, sanitized_devname, fstab_devs):
            updated_line = [sanitized_devname] + line[1:]
        else:
            updated_line = line

        # Ensure all tokens are strings as users may not have quoted them
        # If token is None, replace it with the default value
        for index, token in enumerate(updated_line):
            if token is None:
                updated_line[index] = default_fields[index]
            else:
                updated_line[index] = str(updated_line[index])

        # fill remaining values with defaults from defvals above
        updated_line += default_fields[len(updated_line) :]

        updated_lines.append(updated_line)
    return updated_lines


def remove_nonexistent_devices(mounts: List[List[str]]) -> List[List[str]]:
    """Remove any entries that have a device name that doesn't exist.

    If the second field of a mount line is None (not the string, the value),
    we skip it along with any other entries that came before it that share
    the same device name.
    """
    actlist = []
    dev_denylist = []
    for line in mounts[::-1]:
        if line[1] is None or line[0] in dev_denylist:
            LOG.debug("Skipping nonexistent device named %s", line[0])
            dev_denylist.append(line[0])
        else:
            actlist.append(line)
    # Reverse the list to maintain the original order
    return actlist[::-1]


def add_default_mounts_to_cfg(
    mounts: List[List[str]],
    default_mount_options: str,
    fstab_devs: Dict[str, str],
    device_aliases: Dict[str, str],
    cloud: Cloud,
) -> List[List[str]]:
    """Add default mounts to the user provided mount configuration.

    Add them only if no other entry has the same device name
    """
    new_mounts = copy.deepcopy(mounts)
    for default_mount in [
        ["ephemeral0", "/mnt", "auto", default_mount_options, "0", "2"],
        ["swap", "none", "swap", "sw", "0", "0"],  # Is this used anywhere?
    ]:
        start = default_mount[0]
        sanitized = sanitize_devname(
            start, cloud.device_name_to_device, aliases=device_aliases
        )
        if not sanitized_devname_is_valid(start, sanitized, fstab_devs):
            continue

        # Cast here because the previous call checked for None
        default_mount[0] = cast(str, sanitized)

        default_already_exists = any(
            cfgm[0] == default_mount[0] for cfgm in mounts
        )
        if default_already_exists:
            LOG.debug("Not including %s, already previously included", start)
            continue
        new_mounts.append(default_mount)
    return new_mounts


def add_comment(actlist: List[List[str]]) -> List[List[str]]:
    """Add "comment=cloudconfig" to the mount options of each entry."""
    return [
        entry[:3] + [f"{entry[3]},{MNT_COMMENT}"] + entry[4:]
        for entry in actlist
    ]


def activate_swap_if_needed(actlist: List[List[str]]) -> None:
    """Call 'swapon -a' if any entry has a swap fs type."""
    if any(entry[2] == "swap" for entry in actlist):
        subp.subp(["swapon", "-a"])


def mount_if_needed(
    uses_systemd: bool, changes_made: bool, dirs: List[str]
) -> None:
    """Call 'mount -a' if needed.

    If changes were made, always call 'mount -a'. Otherwise, call 'mount -a'
    if any of the directories in the mount list are not already mounted.
    """
    do_mount = False
    if changes_made:
        do_mount = True
    else:
        mount_points = {
            val["mountpoint"]
            for val in util.mounts().values()
            if "mountpoint" in val
        }
        do_mount = bool(set(dirs).difference(mount_points))

    if do_mount:
        subp.subp(["mount", "-a"])
        if uses_systemd:
            subp.subp(["systemctl", "daemon-reload"])


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """Handle the mounts configuration."""
    # fs_spec, fs_file, fs_vfstype, fs_mntops, fs-freq, fs_passno
    uses_systemd = cloud.distro.uses_systemd()
    default_mount_options = (
        "defaults,nofail,x-systemd.after=cloud-init-network.service,_netdev"
        if uses_systemd
        else "defaults,nobootwait"
    )

    hardcoded_defaults = [None, None, "auto", default_mount_options, "0", "2"]
    default_fields: List[Optional[str]] = cfg.get(
        "mount_default_fields", hardcoded_defaults
    )
    mounts: List[Optional[List[Optional[str]]]] = cfg.get("mounts", [])

    LOG.debug("mounts configuration is %s", mounts)

    fstab_lines, fstab_devs, fstab_removed = parse_fstab()
    device_aliases = cfg.get("device_aliases", {})

    updated_cfg = sanitize_mounts_configuration(
        mounts, fstab_devs, device_aliases, default_fields, cloud
    )
    updated_cfg = add_default_mounts_to_cfg(
        updated_cfg, default_mount_options, fstab_devs, device_aliases, cloud
    )
    updated_cfg = remove_nonexistent_devices(updated_cfg)
    updated_cfg = add_comment(updated_cfg)

    swapfile = handle_swapcfg(cfg.get("swap", {}))
    if swapfile:
        updated_cfg.append([swapfile, "none", "swap", "sw", "0", "0"])

    if len(updated_cfg) == 0:
        # This will only be true if there is no mount configuration at all
        # Even if fstab has no functional changes, we'll get past this point
        # as we remove any 'comment=cloudconfig' lines and then add them back
        # in.
        LOG.debug("No modifications to fstab needed")
        return

    cfg_lines = ["\t".join(entry) for entry in updated_cfg]

    dirs = [d[1] for d in updated_cfg if d[1].startswith("/")]

    for d in dirs:
        try:
            util.ensure_dir(d)
        except Exception:
            util.logexc(LOG, "Failed to make '%s' config-mount", d)

    sadds = [n.replace("\t", " ") for n in cfg_lines]
    sdrops = [n.replace("\t", " ") for n in fstab_removed]

    sops = [f"- {drop}" for drop in sdrops if drop not in sadds] + [
        f"+ {add}" for add in sadds if add not in sdrops
    ]

    fstab_lines.extend(cfg_lines)
    contents = "%s\n" % "\n".join(fstab_lines)
    util.write_file(FSTAB_PATH, contents)

    if sops:
        LOG.debug("Changes to fstab: %s", sops)
    else:
        LOG.debug("No changes to /etc/fstab made.")

    activate_swap_if_needed(updated_cfg)
    mount_if_needed(uses_systemd, bool(sops), dirs)
