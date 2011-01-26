# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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
import glob
import subprocess

def handle(name,cfg,cloud,log,args):
    # remove the static keys from the pristine image
    for f in glob.glob("/etc/ssh/ssh_host_*_key*"):
        try: os.unlink(f)
        except: pass

    if cfg.has_key("ssh_keys"):
        # if there are keys in cloud-config, use them
        key2file = {
            "rsa_private" : ("/etc/ssh/ssh_host_rsa_key", 0600),
            "rsa_public"  : ("/etc/ssh/ssh_host_rsa_key.pub", 0644),
            "dsa_private" : ("/etc/ssh/ssh_host_dsa_key", 0600),
            "dsa_public"  : ("/etc/ssh/ssh_host_dsa_key.pub", 0644)
        }

        for key,val in cfg["ssh_keys"].items():
            if key2file.has_key(key):
                util.write_file(key2file[key][0],val,key2file[key][1])

        priv2pub = { 'rsa_private':'rsa_public', 'dsa_private':'dsa_public' }
        cmd = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'
        for priv,pub in priv2pub.iteritems():
            if pub in cfg['ssh_keys'] or not priv in cfg['ssh_keys']: continue
            pair=(key2file[priv][0], key2file[pub][0])
            subprocess.call(('sh', '-xc', cmd % pair))
            log.debug("generated %s from %s" % pair)
    else:
        # if not, generate them
        genkeys ='ssh-keygen -f /etc/ssh/ssh_host_rsa_key -t rsa -N ""; '
        genkeys+='ssh-keygen -f /etc/ssh/ssh_host_dsa_key -t dsa -N ""; '
        subprocess.call(('sh', '-c', "{ %s } </dev/null" % (genkeys)))

    try:
        user = util.get_cfg_option_str(cfg,'user')
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        keys = cloud.get_public_ssh_keys()

        if cfg.has_key("ssh_authorized_keys"):
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys,user,disable_root)
    except:
        log.warn("applying credentials failed!\n")

    send_ssh_keys_to_console()

def send_ssh_keys_to_console():
    subprocess.call(('/usr/lib/cloud-init/write-ssh-key-fingerprints',))

def apply_credentials(keys, user, disable_root):
    keys = set(keys)
    if user:
        setup_user_keys(keys, user, '')
 
    if disable_root:
        key_prefix = 'command="echo \'Please login as the user \\\"%s\\\" rather than the user \\\"root\\\".\';echo;sleep 10" ' % user
    else:
        key_prefix = ''

    setup_user_keys(keys, 'root', key_prefix)

def setup_user_keys(keys, user, key_prefix):
    import pwd
    saved_umask = os.umask(077)

    pwent = pwd.getpwnam(user)

    ssh_dir = '%s/.ssh' % pwent.pw_dir
    if not os.path.exists(ssh_dir):
        os.mkdir(ssh_dir)
        os.chown(ssh_dir, pwent.pw_uid, pwent.pw_gid)

    authorized_keys = '%s/.ssh/authorized_keys' % pwent.pw_dir
    fp = open(authorized_keys, 'a')
    fp.write(''.join(['%s%s\n' % (key_prefix, key) for key in keys]))
    fp.close()

    os.chown(authorized_keys, pwent.pw_uid, pwent.pw_gid)

    os.umask(saved_umask)


