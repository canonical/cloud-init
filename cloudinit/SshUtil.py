#!/usr/bin/python

import os
import os.path
import cloudinit.util as util

class AuthKeyEntry():
    # lines are options, keytype, base64-encoded key, comment
    # man page says the following which I did not understand:
    #   The options field is optional; its presence is determined by whether
    #   the line starts with a number or not (the options field never starts
    #   with a number)
    options = None
    keytype = None
    base64 = None
    comment = None
    is_comment = False
    line_in = ""

    def __init__(self, line, def_opt=None):
        line=line.rstrip("\n\r")
        self.line_in = line
        if line.startswith("#") or line.strip() == "":
            self.is_comment = True
        else:
            ent = line.strip()
            toks = ent.split(None,3)
            if len(toks) == 1:
                self.base64 = toks[0]
            elif len(toks) == 2:
                (self.base64, self.comment) = toks
            elif len(toks) == 3:
                (self.keytype, self.base64, self.comment) = toks
            elif len(toks) == 4:
                i = 0
                ent = line.strip()
                quoted = False
                # taken from auth_rsa_key_allowed in auth-rsa.c
                try:
                    while (i < len(ent) and 
                           ((quoted) or (ent[i] not in (" ", "\t")))):
                        curc = ent[i]
                        nextc = ent[i + 1]
                        if curc == "\\" and nextc == '"':
                            i = i + 1
                        elif curc == '"':
                            quoted = not quoted
                        i = i + 1
                except IndexError:
                    self.is_comment = True
                    return()

                try:
                    self.options = ent[0:i]
                    (self.keytype, self.base64, self.comment) = \
                        ent[i+1:].split(None,3)
                except ValueError:
                    # we did not understand this line
                    self.is_comment = True

        if self.options == None and def_opt:
            self.options = def_opt

        return

    def debug(self):
        print("line_in=%s\ncomment: %s\noptions=%s\nkeytype=%s\nbase64=%s\ncomment=%s\n" %
            (self.line_in, self.is_comment, self.options, self.keytype, self.base64, self.comment)),
    def __repr__(self):
        if self.is_comment:
            return(self.line_in)
        else:
            toks = [ ]
            for e in (self.options, self.keytype, self.base64, self.comment):
                if e:
                    toks.append(e)
                
            return(' '.join(toks))
            
def update_authorized_keys(fname, keys):
    # keys is a list of AuthKeyEntries
    # key_prefix is the prefix (options) to prepend
    try:
        fp = open(fname, "r")
        lines = fp.readlines() # lines have carriage return
        fp.close()
    except IOError:
        lines = [ ]

    ka_stats = { } # keys_added status
    for k in keys:
        ka_stats[k] = False

    to_add = []
    for key in keys:
        to_add.append(key)

    for i in range(0,len(lines)):
        ent = AuthKeyEntry(lines[i])
        for k in keys:
            if k.base64 == ent.base64 and not k.is_comment:
                ent = k
                try:
                    to_add.remove(k)
                except ValueError:
                    pass
        lines[i] = str(ent)

    # now append any entries we did not match above
    for key in to_add:
        lines.append(str(key))

    if len(lines) == 0:
        return("")
    else:
        return('\n'.join(lines) + "\n")

    
def setup_user_keys(keys, user, key_prefix, log=None):
    import pwd
    saved_umask = os.umask(077)

    pwent = pwd.getpwnam(user)

    ssh_dir = '%s/.ssh' % pwent.pw_dir
    if not os.path.exists(ssh_dir):
        os.mkdir(ssh_dir)
        os.chown(ssh_dir, pwent.pw_uid, pwent.pw_gid)

    try:
        ssh_cfg = parse_ssh_config()
        akeys = ssh_cfg.get("AuthorizedKeysFile","%h/.ssh/authorized_keys")
        akeys = akeys.replace("%h", pwent.pw_dir)
        akeys = akeys.replace("%u", user)
        authorized_keys = akeys
    except Exception:
        authorized_keys = '%s/.ssh/authorized_keys' % pwent.pw_dir
        if log:
            util.logexc(log)

    key_entries = []
    for k in keys:
        ke = AuthKeyEntry(k, def_opt=key_prefix)
        key_entries.append(ke)

    content = update_authorized_keys(authorized_keys, key_entries)
    util.write_file(authorized_keys, content, 0600)

    os.chown(authorized_keys, pwent.pw_uid, pwent.pw_gid)
    util.restorecon_if_possible(ssh_dir, recursive=True)

    os.umask(saved_umask)

if __name__ == "__main__":
    import sys
    # usage: orig_file, new_keys, [key_prefix]
    #   prints out merged, where 'new_keys' will trump old
    ##  example
    ## ### begin authorized_keys ###
    # ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEA28CDAGtxSucHezSKqwh1wAs39xdeZTSVmmyMcKDI5Njnd1d/Uhgj/awxP0Whep8eRSm6F+Xgwi0pH1KNPCszPvq+03K+yi3YkYkQIkVBhctK6AP/UmlVQTVmjJdEvgtrppFTjCzf16q0BT0mXX5YFV3csgm8cJn7UveKHkYjJp8= smoser-work
    # ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZdQueUq5ozemNSj8T7enqKHOEaFoU2VoPgGEWC9RyzSQVeyD6s7APMcE82EtmW4skVEgEGSbDc1pvxzxtchBj78hJP6Cf5TCMFSXw+Fz5rF1dR23QDbN1mkHs7adr8GW4kSWqU7Q7NDwfIrJJtO7Hi42GyXtvEONHbiRPOe8stqUly7MvUoN+5kfjBM8Qqpfl2+FNhTYWpMfYdPUnE7u536WqzFmsaqJctz3gBxH9Ex7dFtrxR4qiqEr9Qtlu3xGn7Bw07/+i1D+ey3ONkZLN+LQ714cgj8fRS4Hj29SCmXp5Kt5/82cD/VN3NtHw== smoser@brickies
    # ### end authorized_keys ###
    # 
    # ### begin new_keys ###
    # ssh-rsa nonmatch smoser@newhost
    # ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEA28CDAGtxSucHezSKqwh1wAs39xdeZTSVmmyMcKDI5Njnd1d/Uhgj/awxP0Whep8eRSm6F+Xgwi0pH1KNPCszPvq+03K+yi3YkYkQIkVBhctK6AP/UmlVQTVmjJdEvgtrppFTjCzf16q0BT0mXX5YFV3csgm8cJn7UveKHkYjJp8= new_comment
    # ### end new_keys ###
    #
    # Then run as:
    #  program authorized_keys new_keys 'no-port-forwarding,command=\"echo hi world;\"'
    def_prefix = None
    orig_key_file = sys.argv[1]
    new_key_file = sys.argv[2]
    if len(sys.argv) > 3:
        def_prefix = sys.argv[3]
    fp = open(new_key_file)

    newkeys = [ ]
    for line in fp.readlines():
        newkeys.append(AuthKeyEntry(line, def_prefix))

    fp.close()
    print update_authorized_keys(orig_key_file, newkeys)

def parse_ssh_config(fname="/etc/ssh/sshd_config"):
    ret = { }
    fp=open(fname)
    for l in fp.readlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        key,val = l.split(None,1)
        ret[key]=val
    fp.close()
    return(ret)

