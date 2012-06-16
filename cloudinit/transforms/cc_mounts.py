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

import cloudinit.util as util
import os
import re
from string import whitespace  # pylint: disable=W0402


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

    # shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1
    shortname_filter = r"^[x]{0,1}[shv]d[a-z][0-9]*$"
    shortname = re.compile(shortname_filter)

    for i in range(len(cfgmnt)):
        # skip something that wasn't a list
        if not isinstance(cfgmnt[i], list):
            continue

        # workaround, allow user to specify 'ephemeral'
        # rather than more ec2 correct 'ephemeral0'
        if cfgmnt[i][0] == "ephemeral":
            cfgmnt[i][0] = "ephemeral0"

        if is_mdname(cfgmnt[i][0]):
            newname = cloud.device_name_to_device(cfgmnt[i][0])
            if not newname:
                log.debug("ignoring nonexistant named mount %s" % cfgmnt[i][0])
                cfgmnt[i][1] = None
            else:
                if newname.startswith("/"):
                    cfgmnt[i][0] = newname
                else:
                    cfgmnt[i][0] = "/dev/%s" % newname
        else:
            if shortname.match(cfgmnt[i][0]):
                cfgmnt[i][0] = "/dev/%s" % cfgmnt[i][0]

        # in case the user did not quote a field (likely fs-freq, fs_passno)
        # but do not convert None to 'None' (LP: #898365)
        for j in range(len(cfgmnt[i])):
            if isinstance(cfgmnt[i][j], int):
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
        devname = cloud.device_name_to_device(defmnt[0])
        if devname is None:
            continue
        if devname.startswith("/"):
            defmnt[0] = devname
        else:
            defmnt[0] = "/dev/%s" % devname

        cfgmnt_has = False
        for cfgm in cfgmnt:
            if cfgm[0] == defmnt[0]:
                cfgmnt_has = True
                break

        if cfgmnt_has:
            continue
        cfgmnt.append(defmnt)

    # now, each entry in the cfgmnt list has all fstab values
    # if the second field is None (not the string, the value) we skip it
    actlist = [x for x in cfgmnt if x[1] is not None]

    if len(actlist) == 0:
        return

    comment = "comment=cloudconfig"
    cc_lines = []
    needswap = False
    dirs = []
    for line in actlist:
        # write 'comment' in the fs_mntops, entry,  claiming this
        line[3] = "%s,comment=cloudconfig" % line[3]
        if line[2] == "swap":
            needswap = True
        if line[1].startswith("/"):
            dirs.append(line[1])
        cc_lines.append('\t'.join(line))

    fstab_lines = []
    fstab = open("/etc/fstab", "r+")
    ws = re.compile("[%s]+" % whitespace)
    for line in fstab.read().splitlines():
        try:
            toks = ws.split(line)
            if toks[3].find(comment) != -1:
                continue
        except:
            pass
        fstab_lines.append(line)

    fstab_lines.extend(cc_lines)

    fstab.seek(0)
    fstab.write("%s\n" % '\n'.join(fstab_lines))
    fstab.truncate()
    fstab.close()

    if needswap:
        try:
            util.subp(("swapon", "-a"))
        except:
            log.warn("Failed to enable swap")

    for d in dirs:
        if os.path.exists(d):
            continue
        try:
            os.makedirs(d)
        except:
            log.warn("Failed to make '%s' config-mount\n", d)

    try:
        util.subp(("mount", "-a"))
    except:
        log.warn("'mount -a' failed")
