# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

from string import whitespace

import logging
import os.path
import re

from cloudinit import type_utils
from cloudinit import util

# Shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1, sr0
SHORTNAME_FILTER = r"^([x]{0,1}[shv]d[a-z][0-9]*|sr[0-9]+)$"
SHORTNAME = re.compile(SHORTNAME_FILTER)
WS = re.compile("[%s]+" % (whitespace))
FSTAB_PATH = "/etc/fstab"

LOG = logging.getLogger(__name__)


def is_mdname(name):
    # return true if this is a metadata service name
    if name in ["ami", "root", "swap"]:
        return True
    # names 'ephemeral0' or 'ephemeral1'
    # 'ebs[0-9]' appears when '--block-device-mapping sdf=snap-d4d90bbc'
    for enumname in ("ephemeral", "ebs"):
        if name.startswith(enumname) and name.find(":") == -1:
            return True
    return False


def sanitize_devname(startname, transformer, log):
    log.debug("Attempting to determine the real name of %s", startname)

    # workaround, allow user to specify 'ephemeral'
    # rather than more ec2 correct 'ephemeral0'
    devname = startname
    if devname == "ephemeral":
        devname = "ephemeral0"
        log.debug("Adjusted mount option from ephemeral to ephemeral0")

    (blockdev, part) = util.expand_dotted_devname(devname)

    if is_mdname(blockdev):
        orig = blockdev
        blockdev = transformer(blockdev)
        if not blockdev:
            return None
        if not blockdev.startswith("/"):
            blockdev = "/dev/%s" % blockdev
        log.debug("Mapped metadata name %s to %s", orig, blockdev)
    else:
        if SHORTNAME.match(startname):
            blockdev = "/dev/%s" % blockdev

    return devnode_for_dev_part(blockdev, part)


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
                    'dd if=/dev/zero "of=$1" bs=1M "count=$2" && '
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
        except:
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
    defvals = [None, None, "auto", "defaults,nobootwait", "0", "2"]
    defvals = cfg.get("mount_default_fields", defvals)

    # these are our default set of mounts
    defmnts = [["ephemeral0", "/mnt", "auto", defvals[3], "0", "2"],
               ["swap", "none", "swap", "sw", "0", "0"]]

    cfgmnt = []
    if "mounts" in cfg:
        cfgmnt = cfg["mounts"]

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
    for line in util.load_file(FSTAB_PATH).splitlines():
        try:
            toks = WS.split(line)
            if toks[3].find(comment) != -1:
                continue
        except:
            pass
        fstab_lines.append(line)

    fstab_lines.extend(cc_lines)
    contents = "%s\n" % ('\n'.join(fstab_lines))
    util.write_file(FSTAB_PATH, contents)

    if needswap:
        try:
            util.subp(("swapon", "-a"))
        except:
            util.logexc(log, "Activating swap via 'swapon -a' failed")

    for d in dirs:
        try:
            util.ensure_dir(d)
        except:
            util.logexc(log, "Failed to make '%s' config-mount", d)

    try:
        util.subp(("mount", "-a"))
    except:
        util.logexc(log, "Activating mounts via 'mount -a' failed")


def devnode_for_dev_part(device, partition):
    """
    Find the name of the partition. While this might seem rather
    straight forward, its not since some devices are '<device><partition>'
    while others are '<device>p<partition>'. For example, /dev/xvda3 on EC2
    will present as /dev/xvda3p1 for the first partition since /dev/xvda3 is
    a block device.
    """
    if not os.path.exists(device):
        return None

    short_name = os.path.basename(device)
    sys_path = "/sys/block/%s" % short_name

    if not os.path.exists(sys_path):
        LOG.debug("did not find entry for %s in /sys/block", short_name)
        return None

    sys_long_path = sys_path + "/" + short_name

    if partition is not None:
        partition = str(partition)

    if partition is None:
        valid_mappings = [sys_long_path + "1", sys_long_path + "p1"]
    elif partition != "0":
        valid_mappings = [sys_long_path + "%s" % partition,
                          sys_long_path + "p%s" % partition]
    else:
        valid_mappings = []

    for cdisk in valid_mappings:
        if not os.path.exists(cdisk):
            continue

        dev_path = "/dev/%s" % os.path.basename(cdisk)
        if os.path.exists(dev_path):
            return dev_path

    if partition is None or partition == "0":
        return device

    LOG.debug("Did not fine partition %s for device %s", partition, device)
    return None
