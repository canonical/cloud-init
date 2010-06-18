import cloudinit.util as util
import os
import re
import string

def handle(name,cfg,cloud,log,args):
    # these are our default set of mounts
    defmnts = [ [ "ephemeral0", "/mnt", "auto", "defaults", "0", "0" ],
                [ "swap", "none", "swap", "sw", "0", "0" ] ]

    # fs_spec, fs_file, fs_vfstype, fs_mntops, fs-freq, fs_passno
    defvals = [ None, None, "auto", "defaults", "0", "0" ]

    cfgmnt = [ ]
    if cfg.has_key("mounts"):
        cfgmnt = cfg["mounts"]

    for i in range(len(cfgmnt)):
        # skip something that wasn't a list
        if not isinstance(cfgmnt[i],list): continue

        # workaround, allow user to specify 'ephemeral'
        # rather than more ec2 correct 'ephemeral0'
        if cfgmnt[i][0] == "ephemeral":
            cfgmnt[i][0] = "ephemeral0"

        newname = cfgmnt[i][0]
        if not newname.startswith("/"):
            newname = cloud.device_name_to_device(cfgmnt[i][0])
        if newname is not None:
            cfgmnt[i][0] = newname
        else:
            # there is no good way of differenciating between
            # a name that *couldn't* exist in the md service and
            # one that merely didnt
            # in order to allow user to specify 'sda3' rather
            # than '/dev/sda3', go through some hoops
            ok = False
            for f in [ "/", "sd", "hd", "vd", "xvd" ]:
                if cfgmnt[i][0].startswith(f):
                    ok = True
                    break
            if not ok:
                cfgmnt[i][1] = None

    for i in range(len(cfgmnt)):
        # fill in values with 
        for j in range(len(defvals)):
            if len(cfgmnt[i]) <= j:
                cfgmnt[i].append(defvals[j])
            elif cfgmnt[i][j] is None:
                cfgmnt[i][j] = defvals[j]

        if not cfgmnt[i][0].startswith("/"):
            cfgmnt[i][0]="/dev/%s" % cfgmnt[i][0]

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
        if devname is None: continue
        if devname.startswith("/"):
            defmnt[0] = devname
        else:
            defmnt[0] = "/dev/%s" % devname

        cfgmnt_has = False
        for cfgm in cfgmnt:
            if cfgm[0] == defmnt[0]:
                cfgmnt_has = True
                break
        
        if cfgmnt_has: continue
        cfgmnt.append(defmnt)


    # now, each entry in the cfgmnt list has all fstab values
    # if the second field is None (not the string, the value) we skip it
    actlist = filter(lambda x: x[1] is not None, cfgmnt)

    if len(actlist) == 0: return

    comment="comment=cloudconfig"
    cc_lines = [ ]
    needswap = False
    dirs = [ ]
    for line in actlist:
        # write 'comment' in the fs_mntops, entry,  claiming this
        line[3]="%s,comment=cloudconfig" % line[3]
        if line[2] == "swap": needswap = True
        if line[1].startswith("/"): dirs.append(line[1])
        cc_lines.append('\t'.join(line))

    fstab_lines = [ ]
    fstab=open("/etc/fstab","r+")
    ws = re.compile("[%s]+" % string.whitespace)
    for line in fstab.read().splitlines():
        try:
            toks = ws.split(line)
            if toks[3].find(comment) != -1: continue
        except:
            pass
        fstab_lines.append(line)

    fstab_lines.extend(cc_lines)
        
    fstab.seek(0)
    fstab.write("%s\n" % '\n'.join(fstab_lines))
    fstab.truncate()
    fstab.close()

    if needswap:
        try: util.subp(("swapon", "-a"))
        except: log.warn("Failed to enable swap")

    for d in dirs:
        if os.path.exists(d): continue
        try: os.makedirs(d)
        except: log.warn("Failed to make '%s' config-mount\n",d)

    try: util.subp(("mount","-a"))
    except: pass
