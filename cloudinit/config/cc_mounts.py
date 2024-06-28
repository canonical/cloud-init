# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Mounts: Configure mount points and swap files"""

import logging
import math
import os
import re
from string import whitespace

from cloudinit import subp, type_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_mounts",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

# Shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1, sr0
DEVICE_NAME_FILTER = r"^([x]{0,1}[shv]d[a-z][0-9]*|sr[0-9]+)$"
DEVICE_NAME_RE = re.compile(DEVICE_NAME_FILTER)
# Name matches 'server:/path'
NETWORK_NAME_FILTER = r"^.+:.*"
NETWORK_NAME_RE = re.compile(NETWORK_NAME_FILTER)
WS = re.compile("[%s]+" % (whitespace))
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
    if NETWORK_NAME_RE.match(name):
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
        if DEVICE_NAME_RE.match(startname):
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

    util.log_time(
        LOG.debug,
        msg="Setting up swap file",
        func=create_swapfile,
        args=[fname, mibsize],
    )

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


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # fs_spec, fs_file, fs_vfstype, fs_mntops, fs-freq, fs_passno
    def_mnt_opts = "defaults,nobootwait"
    uses_systemd = cloud.distro.uses_systemd()
    if uses_systemd:
        def_mnt_opts = (
            "defaults,nofail,x-systemd.after=cloud-init.service,_netdev"
        )

    defvals = [None, None, "auto", def_mnt_opts, "0", "2"]
    defvals = cfg.get("mount_default_fields", defvals)

    # these are our default set of mounts
    defmnts: list = [
        ["ephemeral0", "/mnt", "auto", defvals[3], "0", "2"],
        ["swap", "none", "swap", "sw", "0", "0"],
    ]

    cfgmnt = []
    if "mounts" in cfg:
        cfgmnt = cfg["mounts"]

    LOG.debug("mounts configuration is %s", cfgmnt)

    fstab_lines = []
    fstab_devs = {}
    fstab_removed = []

    if os.path.exists(FSTAB_PATH):
        for line in util.load_text_file(FSTAB_PATH).splitlines():
            if MNT_COMMENT in line:
                fstab_removed.append(line)
                continue

            try:
                toks = WS.split(line)
            except Exception:
                pass
            fstab_devs[toks[0]] = line
            fstab_lines.append(line)

    device_aliases = cfg.get("device_aliases", {})

    for i in range(len(cfgmnt)):
        # skip something that wasn't a list
        if not isinstance(cfgmnt[i], list):
            LOG.warning(
                "Mount option %s not a list, got a %s instead",
                (i + 1),
                type_utils.obj_name(cfgmnt[i]),
            )
            continue

        start = str(cfgmnt[i][0])
        sanitized = sanitize_devname(
            start, cloud.device_name_to_device, aliases=device_aliases
        )
        if sanitized != start:
            LOG.debug("changed %s => %s", start, sanitized)

        if sanitized is None:
            LOG.debug("Ignoring nonexistent named mount %s", start)
            continue
        elif sanitized in fstab_devs:
            LOG.info(
                "Device %s already defined in fstab: %s",
                sanitized,
                fstab_devs[sanitized],
            )
            continue

        cfgmnt[i][0] = sanitized

        # in case the user did not quote a field (likely fs-freq, fs_passno)
        # but do not convert None to 'None' (LP: #898365)
        for j in range(len(cfgmnt[i])):
            if cfgmnt[i][j] is None:
                continue
            else:
                cfgmnt[i][j] = str(cfgmnt[i][j])

    for i in range(len(cfgmnt)):
        # fill in values with defaults from defvals above
        for j in range(len(defvals)):
            if len(cfgmnt[i]) <= j:
                cfgmnt[i].append(defvals[j])
            elif cfgmnt[i][j] is None:
                cfgmnt[i][j] = defvals[j]

        # if the second entry in the list is 'None' this
        # clears all previous entries of that same 'fs_spec'
        # (fs_spec is the first field in /etc/fstab, ie, that device)
        if cfgmnt[i][1] is None:
            for j in range(i):
                if cfgmnt[j][0] == cfgmnt[i][0]:
                    cfgmnt[j][1] = None

    # for each of the "default" mounts, add them only if no other
    # entry has the same device name
    for defmnt in defmnts:
        start = defmnt[0]
        sanitized = sanitize_devname(
            start, cloud.device_name_to_device, aliases=device_aliases
        )
        if sanitized != start:
            LOG.debug("changed default device %s => %s", start, sanitized)

        if sanitized is None:
            LOG.debug("Ignoring nonexistent default named mount %s", start)
            continue
        elif sanitized in fstab_devs:
            LOG.debug(
                "Device %s already defined in fstab: %s",
                sanitized,
                fstab_devs[sanitized],
            )
            continue

        defmnt[0] = sanitized

        cfgmnt_has = False
        for cfgm in cfgmnt:
            if cfgm[0] == defmnt[0]:
                cfgmnt_has = True
                break

        if cfgmnt_has:
            LOG.debug("Not including %s, already previously included", start)
            continue
        cfgmnt.append(defmnt)

    # now, each entry in the cfgmnt list has all fstab values
    # if the second field is None (not the string, the value) we skip it
    actlist = []
    for x in cfgmnt:
        if x[1] is None:
            LOG.debug("Skipping nonexistent device named %s", x[0])
        else:
            actlist.append(x)

    swapret = handle_swapcfg(cfg.get("swap", {}))
    if swapret:
        actlist.append([swapret, "none", "swap", "sw", "0", "0"])

    if len(actlist) == 0:
        LOG.debug("No modifications to fstab needed")
        return

    cc_lines = []
    needswap = False
    need_mount_all = False
    dirs = []
    for entry in actlist:
        # write 'comment' in the fs_mntops, entry,  claiming this
        entry[3] = "%s,%s" % (entry[3], MNT_COMMENT)
        if entry[2] == "swap":
            needswap = True
        if entry[1].startswith("/"):
            dirs.append(entry[1])
        cc_lines.append("\t".join(entry))

    mount_points = [
        v["mountpoint"] for k, v in util.mounts().items() if "mountpoint" in v
    ]
    for d in dirs:
        try:
            util.ensure_dir(d)
        except Exception:
            util.logexc(LOG, "Failed to make '%s' config-mount", d)
        # dirs is list of directories on which a volume should be mounted.
        # If any of them does not already show up in the list of current
        # mount points, we will definitely need to do mount -a.
        if not need_mount_all and d not in mount_points:
            need_mount_all = True

    sadds = [WS.sub(" ", n) for n in cc_lines]
    sdrops = [WS.sub(" ", n) for n in fstab_removed]

    sops = ["- " + drop for drop in sdrops if drop not in sadds] + [
        "+ " + add for add in sadds if add not in sdrops
    ]

    fstab_lines.extend(cc_lines)
    contents = "%s\n" % "\n".join(fstab_lines)
    util.write_file(FSTAB_PATH, contents)

    activate_cmds = []
    if needswap:
        activate_cmds.append(["swapon", "-a"])

    if len(sops) == 0:
        LOG.debug("No changes to /etc/fstab made.")
    else:
        LOG.debug("Changes to fstab: %s", sops)
        need_mount_all = True

    if need_mount_all:
        activate_cmds.append(["mount", "-a"])
        if uses_systemd:
            activate_cmds.append(["systemctl", "daemon-reload"])

    fmt = "Activating swap and mounts with: %s"
    for cmd in activate_cmds:
        fmt = "Activate mounts: %s:" + " ".join(cmd)
        try:
            subp.subp(cmd)
            LOG.debug(fmt, "PASS")
        except subp.ProcessExecutionError:
            LOG.warning(fmt, "FAIL")
            util.logexc(LOG, fmt, "FAIL")
