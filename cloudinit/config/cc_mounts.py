# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Mounts
------
**Summary:** configure mount points and swap files

This module can add or remove mountpoints from ``/etc/fstab`` as well as
configure swap. The ``mounts`` config key takes a list of fstab entries to add.
Each entry is specified as a list of ``[ fs_spec, fs_file, fs_vfstype,
fs_mntops, fs-freq, fs_passno ]``. For more information on these options,
consult the manual for ``/etc/fstab``. When specifying the ``fs_spec``, if the
device name starts with one of ``xvd``, ``sd``, ``hd``, or ``vd``, the leading
``/dev`` may be omitted.

In order to remove a previously listed mount, an entry can be added to the
mounts list containing ``fs_spec`` for the device to be removed but no
mountpoint (i.e. ``[ sda1 ]`` or ``[ sda1, null ]``).

The ``mount_default_fields`` config key allows default options to be specified
for the values in a ``mounts`` entry that are not specified, aside from the
``fs_spec`` and the ``fs_file``. If specified, this must be a list containing 7
values. It defaults to::

    mount_default_fields: [none, none, "auto", "defaults,nobootwait", "0", "2"]

On a systemd booted system that default is the mostly equivalent::

    mount_default_fields: [none, none, "auto",
       "defaults,nofail,x-systemd.requires=cloud-init.service", "0", "2"]

Note that `nobootwait` is an upstart specific boot option that somewhat
equates to the more standard `nofail`.

Swap files can be configured by setting the path to the swap file to create
with ``filename``, the size of the swap file with ``size`` maximum size of
the swap file if using an ``size: auto`` with ``maxsize``. By default no
swap file is created.

**Internal name:** ``cc_mounts``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    mounts:
        - [ /dev/ephemeral0, /mnt, auto, "defaults,noexec" ]
        - [ sdc, /opt/data ]
        - [ xvdh, /opt/data, "auto", "defaults,nofail", "0", "0" ]
    mount_default_fields: [None, None, "auto", "defaults,nofail", "0", "2"]
    swap:
        filename: <file>
        size: <"auto"/size in bytes>
        maxsize: <size in bytes>
"""

from string import whitespace

import logging
import os.path
import re

from cloudinit import type_utils
from cloudinit import util

# Shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1, sr0
DEVICE_NAME_FILTER = r"^([x]{0,1}[shv]d[a-z][0-9]*|sr[0-9]+)$"
DEVICE_NAME_RE = re.compile(DEVICE_NAME_FILTER)
WS = re.compile("[%s]+" % (whitespace))
FSTAB_PATH = "/etc/fstab"

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


def _get_nth_partition_for_device(device_path, partition_number):
    potential_suffixes = [str(partition_number), 'p%s' % (partition_number,),
                          '-part%s' % (partition_number,)]
    for suffix in potential_suffixes:
        potential_partition_device = '%s%s' % (device_path, suffix)
        if os.path.exists(potential_partition_device):
            return potential_partition_device
    return None


def _is_block_device(device_path, partition_path=None):
    device_name = os.path.realpath(device_path).split('/')[-1]
    sys_path = os.path.join('/sys/block/', device_name)
    if partition_path is not None:
        sys_path = os.path.join(
            sys_path, os.path.realpath(partition_path).split('/')[-1])
    return os.path.exists(sys_path)


def sanitize_devname(startname, transformer, log):
    log.debug("Attempting to determine the real name of %s", startname)

    # workaround, allow user to specify 'ephemeral'
    # rather than more ec2 correct 'ephemeral0'
    devname = startname
    if devname == "ephemeral":
        devname = "ephemeral0"
        log.debug("Adjusted mount option from ephemeral to ephemeral0")

    device_path, partition_number = util.expand_dotted_devname(devname)

    if is_meta_device_name(device_path):
        orig = device_path
        device_path = transformer(device_path)
        if not device_path:
            return None
        if not device_path.startswith("/"):
            device_path = "/dev/%s" % (device_path,)
        log.debug("Mapped metadata name %s to %s", orig, device_path)
    else:
        if DEVICE_NAME_RE.match(startname):
            device_path = "/dev/%s" % (device_path,)

    partition_path = None
    if partition_number is None:
        partition_path = _get_nth_partition_for_device(device_path, 1)
    else:
        partition_path = _get_nth_partition_for_device(device_path,
                                                       partition_number)
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
        memsize = util.read_meminfo()['total']

    GB = 2 ** 30
    sugg_max = 8 * GB

    info = {'avail': 'na', 'max_in': maxsize, 'mem': memsize}

    if fsys is None and maxsize is None:
        # set max to 8GB default if no filesystem given
        maxsize = sugg_max
    elif fsys:
        statvfs = os.statvfs(fsys)
        avail = statvfs.f_frsize * statvfs.f_bfree
        info['avail'] = avail

        if maxsize is None:
            # set to 25% of filesystem space
            maxsize = min(int(avail / 4), sugg_max)
        elif maxsize > ((avail * .9)):
            # set to 90% of available disk space
            maxsize = int(avail * .9)
    elif maxsize is None:
        maxsize = sugg_max

    info['max'] = maxsize

    formulas = [
        # < 1G: swap = double memory
        (1 * GB, lambda x: x * 2),
        # < 2G: swap = 2G
        (2 * GB, lambda x: 2 * GB),
        # < 4G: swap = memory
        (4 * GB, lambda x: x),
        # < 16G: 4G
        (16 * GB, lambda x: 4 * GB),
        # < 64G: 1/2 M up to max
        (64 * GB, lambda x: x / 2),
    ]

    size = None
    for top, func in formulas:
        if memsize <= top:
            size = min(func(memsize), maxsize)
            # if less than 1/2 memory and not much, return 0
            if size < (memsize / 2) and size < 4 * GB:
                size = 0
                break
            break

    if size is not None:
        size = maxsize

    info['size'] = size

    MB = 2 ** 20
    pinfo = {}
    for k, v in info.items():
        if isinstance(v, int):
            pinfo[k] = "%s MB" % (v / MB)
        else:
            pinfo[k] = v

    LOG.debug("suggest %(size)s swap for %(mem)s memory with '%(avail)s'"
              " disk given max=%(max_in)s [max=%(max)s]'" % pinfo)
    return size


def setup_swapfile(fname, size=None, maxsize=None):
    """
    fname: full path string of filename to setup
    size: the size to create. set to "auto" for recommended
    maxsize: the maximum size
    """
    tdir = os.path.dirname(fname)
    if str(size).lower() == "auto":
        try:
            memsize = util.read_meminfo()['total']
        except IOError as e:
            LOG.debug("Not creating swap. failed to read meminfo")
            return

        util.ensure_dir(tdir)
        size = suggested_swapsize(fsys=tdir, maxsize=maxsize,
                                  memsize=memsize)

    if not size:
        LOG.debug("Not creating swap: suggested size was 0")
        return

    mbsize = str(int(size / (2 ** 20)))
    msg = "creating swap file '%s' of %sMB" % (fname, mbsize)
    try:
        util.ensure_dir(tdir)
        util.log_time(LOG.debug, msg, func=util.subp,
                      args=[['sh', '-c',
                            ('rm -f "$1" && umask 0066 && '
                             '{ fallocate -l "${2}M" "$1" || '
                             ' dd if=/dev/zero "of=$1" bs=1M "count=$2"; } && '
                             'mkswap "$1" || { r=$?; rm -f "$1"; exit $r; }'),
                             'setup_swap', fname, mbsize]])

    except Exception as e:
        raise IOError("Failed %s: %s" % (msg, e))

    return fname


def handle_swapcfg(swapcfg):
    """handle the swap config, calling setup_swap if necessary.
       return None or (filename, size)
    """
    if not isinstance(swapcfg, dict):
        LOG.warn("input for swap config was not a dict.")
        return None

    fname = swapcfg.get('filename', '/swap.img')
    size = swapcfg.get('size', 0)
    maxsize = swapcfg.get('maxsize', None)

    if not (size and fname):
        LOG.debug("no need to setup swap")
        return

    if os.path.exists(fname):
        if not os.path.exists("/proc/swaps"):
            LOG.debug("swap file %s existed. no /proc/swaps. Being safe.",
                      fname)
            return fname
        try:
            for line in util.load_file("/proc/swaps").splitlines():
                if line.startswith(fname + " "):
                    LOG.debug("swap file %s already in use.", fname)
                    return fname
            LOG.debug("swap file %s existed, but not in /proc/swaps", fname)
        except Exception:
            LOG.warn("swap file %s existed. Error reading /proc/swaps", fname)
            return fname

    try:
        if isinstance(size, str) and size != "auto":
            size = util.human2bytes(size)
        if isinstance(maxsize, str):
            maxsize = util.human2bytes(maxsize)
        return setup_swapfile(fname=fname, size=size, maxsize=maxsize)

    except Exception as e:
        LOG.warn("failed to setup swap: %s", e)

    return None


def handle(_name, cfg, cloud, log, _args):
    # fs_spec, fs_file, fs_vfstype, fs_mntops, fs-freq, fs_passno
    def_mnt_opts = "defaults,nobootwait"
    uses_systemd = cloud.distro.uses_systemd()
    if uses_systemd:
        def_mnt_opts = "defaults,nofail,x-systemd.requires=cloud-init.service"

    defvals = [None, None, "auto", def_mnt_opts, "0", "2"]
    defvals = cfg.get("mount_default_fields", defvals)

    # these are our default set of mounts
    defmnts = [["ephemeral0", "/mnt", "auto", defvals[3], "0", "2"],
               ["swap", "none", "swap", "sw", "0", "0"]]

    cfgmnt = []
    if "mounts" in cfg:
        cfgmnt = cfg["mounts"]

    LOG.debug("mounts configuration is %s", cfgmnt)

    for i in range(len(cfgmnt)):
        # skip something that wasn't a list
        if not isinstance(cfgmnt[i], list):
            log.warn("Mount option %s not a list, got a %s instead",
                     (i + 1), type_utils.obj_name(cfgmnt[i]))
            continue

        start = str(cfgmnt[i][0])
        sanitized = sanitize_devname(start, cloud.device_name_to_device, log)
        if sanitized is None:
            log.debug("Ignorming nonexistant named mount %s", start)
            continue

        if sanitized != start:
            log.debug("changed %s => %s" % (start, sanitized))
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
        sanitized = sanitize_devname(start, cloud.device_name_to_device, log)
        if sanitized is None:
            log.debug("Ignoring nonexistant default named mount %s", start)
            continue
        if sanitized != start:
            log.debug("changed default device %s => %s" % (start, sanitized))
        defmnt[0] = sanitized

        cfgmnt_has = False
        for cfgm in cfgmnt:
            if cfgm[0] == defmnt[0]:
                cfgmnt_has = True
                break

        if cfgmnt_has:
            log.debug(("Not including %s, already"
                       " previously included"), start)
            continue
        cfgmnt.append(defmnt)

    # now, each entry in the cfgmnt list has all fstab values
    # if the second field is None (not the string, the value) we skip it
    actlist = []
    for x in cfgmnt:
        if x[1] is None:
            log.debug("Skipping non-existent device named %s", x[0])
        else:
            actlist.append(x)

    swapret = handle_swapcfg(cfg.get('swap', {}))
    if swapret:
        actlist.append([swapret, "none", "swap", "sw", "0", "0"])

    if len(actlist) == 0:
        log.debug("No modifications to fstab needed.")
        return

    comment = "comment=cloudconfig"
    cc_lines = []
    needswap = False
    dirs = []
    for line in actlist:
        # write 'comment' in the fs_mntops, entry,  claiming this
        line[3] = "%s,%s" % (line[3], comment)
        if line[2] == "swap":
            needswap = True
        if line[1].startswith("/"):
            dirs.append(line[1])
        cc_lines.append('\t'.join(line))

    fstab_lines = []
    removed = []
    for line in util.load_file(FSTAB_PATH).splitlines():
        try:
            toks = WS.split(line)
            if toks[3].find(comment) != -1:
                removed.append(line)
                continue
        except Exception:
            pass
        fstab_lines.append(line)

    for d in dirs:
        try:
            util.ensure_dir(d)
        except Exception:
            util.logexc(log, "Failed to make '%s' config-mount", d)

    sadds = [WS.sub(" ", n) for n in cc_lines]
    sdrops = [WS.sub(" ", n) for n in removed]

    sops = (["- " + drop for drop in sdrops if drop not in sadds] +
            ["+ " + add for add in sadds if add not in sdrops])

    fstab_lines.extend(cc_lines)
    contents = "%s\n" % ('\n'.join(fstab_lines))
    util.write_file(FSTAB_PATH, contents)

    activate_cmds = []
    if needswap:
        activate_cmds.append(["swapon", "-a"])

    if len(sops) == 0:
        log.debug("No changes to /etc/fstab made.")
    else:
        log.debug("Changes to fstab: %s", sops)
        activate_cmds.append(["mount", "-a"])
        if uses_systemd:
            activate_cmds.append(["systemctl", "daemon-reload"])

    fmt = "Activating swap and mounts with: %s"
    for cmd in activate_cmds:
        fmt = "Activate mounts: %s:" + ' '.join(cmd)
        try:
            util.subp(cmd)
            log.debug(fmt, "PASS")
        except util.ProcessExecutionError:
            log.warn(fmt, "FAIL")
            util.logexc(log, fmt, "FAIL")

# vi: ts=4 expandtab
