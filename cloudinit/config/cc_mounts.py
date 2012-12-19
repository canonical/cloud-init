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

from string import whitespace  # pylint: disable=W0402

import re

from cloudinit import util

# Shortname matches 'sda', 'sda1', 'xvda', 'hda', 'sdb', xvdb, vda, vdd1
SHORTNAME_FILTER = r"^[x]{0,1}[shv]d[a-z][0-9]*$"
SHORTNAME = re.compile(SHORTNAME_FILTER)
WS = re.compile("[%s]+" % (whitespace))
FSTAB_PATH = "/etc/fstab"


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

    for i in range(len(cfgmnt)):
        # skip something that wasn't a list
        if not isinstance(cfgmnt[i], list):
            log.warn("Mount option %s not a list, got a %s instead",
                     (i + 1), util.obj_name(cfgmnt[i]))
            continue

        startname = str(cfgmnt[i][0])
        log.debug("Attempting to determine the real name of %s", startname)

        # workaround, allow user to specify 'ephemeral'
        # rather than more ec2 correct 'ephemeral0'
        if startname == "ephemeral":
            cfgmnt[i][0] = "ephemeral0"
            log.debug(("Adjusted mount option %s "
                       "name from ephemeral to ephemeral0"), (i + 1))

        if is_mdname(startname):
            newname = cloud.device_name_to_device(startname)
            if not newname:
                log.debug("Ignoring nonexistant named mount %s", startname)
                cfgmnt[i][1] = None
            else:
                renamed = newname
                if not newname.startswith("/"):
                    renamed = "/dev/%s" % newname
                cfgmnt[i][0] = renamed
                log.debug("Mapped metadata name %s to %s", startname, renamed)
        else:
            if SHORTNAME.match(startname):
                renamed = "/dev/%s" % startname
                log.debug("Mapped shortname name %s to %s", startname, renamed)
                cfgmnt[i][0] = renamed

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
        startname = defmnt[0]
        devname = cloud.device_name_to_device(startname)
        if devname is None:
            log.debug("Ignoring nonexistant named default mount %s", startname)
            continue
        if devname.startswith("/"):
            defmnt[0] = devname
        else:
            defmnt[0] = "/dev/%s" % devname

        log.debug("Mapped default device %s to %s", startname, defmnt[0])

        cfgmnt_has = False
        for cfgm in cfgmnt:
            if cfgm[0] == defmnt[0]:
                cfgmnt_has = True
                break

        if cfgmnt_has:
            log.debug(("Not including %s, already"
                       " previously included"), startname)
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
