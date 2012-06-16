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

import os
import glob

from cloudinit import util
from cloudinit import ssh_util

DISABLE_ROOT_OPTS = ( "no-port-forwarding,no-agent-forwarding," 
"no-X11-forwarding,command=\"echo \'Please login as the user \\\"$USER\\\" " 
"rather than the user \\\"root\\\".\';echo;sleep 10\"")

key2file = {
    "rsa_private": ("/etc/ssh/ssh_host_rsa_key", 0600),
    "rsa_public": ("/etc/ssh/ssh_host_rsa_key.pub", 0644),
    "dsa_private": ("/etc/ssh/ssh_host_dsa_key", 0600),
    "dsa_public": ("/etc/ssh/ssh_host_dsa_key.pub", 0644),
    "ecdsa_private": ("/etc/ssh/ssh_host_ecdsa_key", 0600),
    "ecdsa_public": ("/etc/ssh/ssh_host_ecdsa_key.pub", 0644),
}

priv2pub = {
    'rsa_private': 'rsa_public', 
    'dsa_private': 'dsa_public',
    'ecdsa_private': 'ecdsa_public',
}

key_gen_tpl = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'

generate_keys = ['rsa', 'dsa', 'ecdsa']


def handle(_name, cfg, cloud, log, _args):

    # remove the static keys from the pristine image
    if cfg.get("ssh_deletekeys", True):
        for f in glob.glob("/etc/ssh/ssh_host_*key*"):
            try:
                util.del_file(f)
            except:
                util.logexc(log, "Failed deleting key file %s", f)
    
    if "ssh_keys" in cfg:
        # if there are keys in cloud-config, use them
        for (key, val) in cfg["ssh_keys"].iteritems():
            if key in key2file:
                tgt_fn = key2file[key][0]
                tgt_perms = key2file[key][1]
                util.write_file(tgt_fn, val, tgt_perms)
    
        cmd = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'
        for priv, pub in priv2pub.iteritems():
            if pub in cfg['ssh_keys'] or not priv in cfg['ssh_keys']:
                continue
            pair = (key2file[priv][0], key2file[pub][0])
            cmd = ['sh', '-xc', key_gen_tpl % pair]
            try:
                # TODO: Is this guard needed?
                with util.SeLinuxGuard("/etc/ssh", recursive=True):
                    util.subp(cmd, capture=False)
                log.debug("Generated a key for %s from %s", pair[0], pair[1])
            except:
                util.logexc(log, "Failed generated a key for %s from %s", pair[0], pair[1])
    else:
        # if not, generate them
        for keytype in util.get_cfg_option_list_or_str(cfg, 'ssh_genkeytypes', generate_keys):
            keyfile = '/etc/ssh/ssh_host_%s_key' % keytype
            if not os.path.exists(keyfile):
                cmd = ['ssh-keygen', '-t', keytype, '-N', '', '-f', keyfile]
                try:
                    # TODO: Is this guard needed?
                    with util.SeLinuxGuard("/etc/ssh", recursive=True):
                        util.subp(cmd, capture=False)
                except:
                    util.logexc(log, "Failed generating key type %s to file %s", keytype, keyfile)

    try:
        user = util.get_cfg_option_str(cfg, 'user')
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        disable_root_opts = util.get_cfg_option_str(cfg, "disable_root_opts",
            DISABLE_ROOT_OPTS)

        keys = cloud.get_public_ssh_keys() or []
        if "ssh_authorized_keys" in cfg:
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys, user, disable_root, disable_root_opts, log)
    except:
        util.logexc(log, "Applying ssh credentials failed!")


def apply_credentials(keys, user, disable_root,
                      disable_root_opts=DISABLE_ROOT_OPTS, log=None):

    keys = set(keys)
    if user:
        ssh_util.setup_user_keys(keys, user, '')

    if disable_root and user:
        key_prefix = disable_root_opts.replace('$USER', user)
    else:
        key_prefix = ''

    ssh_util.setup_user_keys(keys, 'root', key_prefix)
