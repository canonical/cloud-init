# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
SSH
---
**Summary:** configure ssh and ssh keys

This module handles most configuration for ssh and ssh keys. Many images have
default ssh keys, which can be removed using ``ssh_deletekeys``. Since removing
default keys is usually the desired behavior this option is enabled by default.

Keys can be added using the ``ssh_keys`` configuration key. The argument to
this config key should be a dictionary entries for the public and private keys
of each desired key type. Entries in the ``ssh_keys`` config dict should
have keys in the format ``<key type>_private`` and ``<key type>_public``, e.g.
``rsa_private: <key>`` and ``rsa_public: <key>``. See below for supported key
types. Not all key types have to be specified, ones left unspecified will not
be used. If this config option is used, then no keys will be generated.

.. note::
    when specifying private keys in cloud-config, care should be taken to
    ensure that the communication between the data source and the instance is
    secure

.. note::
    to specify multiline private keys, use yaml multiline syntax

If no keys are specified using ``ssh_keys``, then keys will be generated using
``ssh-keygen``. By default one public/private pair of each supported key type
will be generated. The key types to generate can be specified using the
``ssh_genkeytypes`` config flag, which accepts a list of key types to use. For
each key type for which this module has been instructed to create a keypair, if
a key of the same type is already present on the system (i.e. if
``ssh_deletekeys`` was false), no key will be generated.

Supported key types for the ``ssh_keys`` and the ``ssh_genkeytypes`` config
flags are:

    - rsa
    - dsa
    - ecdsa
    - ed25519

Root login can be enabled/disabled using the ``disable_root`` config key. Root
login options can be manually specified with ``disable_root_opts``. If
``disable_root_opts`` is specified and contains the string ``$USER``,
it will be replaced with the username of the default user. By default,
root login is disabled, and root login opts are set to::

    no-port-forwarding,no-agent-forwarding,no-X11-forwarding

Authorized keys for the default user/first user defined in ``users`` can be
specified using `ssh_authorized_keys``. Keys should be specified as a list of
public keys.

.. note::
    see the ``cc_set_passwords`` module documentation to enable/disable ssh
    password authentication

**Internal name:** ``cc_ssh``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    ssh_deletekeys: <true/false>
    ssh_keys:
        rsa_private: |
            -----BEGIN RSA PRIVATE KEY-----
            MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+00R7VVu2iV9Qco
            ...
            -----END RSA PRIVATE KEY-----
        rsa_public: ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEAoPRhIfLvedSDKw7Xd ...
        dsa_private: |
            -----BEGIN DSA PRIVATE KEY-----
            MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+00R7VVu2iV9Qco
            ...
            -----END DSA PRIVATE KEY-----
        dsa_public: ssh-dsa AAAAB3NzaC1yc2EAAAABIwAAAGEAoPRhIfLvedSDKw7Xd ...
    ssh_genkeytypes: <key type>
    disable_root: <true/false>
    disable_root_opts: <disable root options string>
    ssh_authorized_keys:
        - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEA3FSyQwBI6Z+nCSjUU ...
        - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZ ...
"""

import glob
import os
import sys

from cloudinit.distros import ug_util
from cloudinit import ssh_util
from cloudinit import util


GENERATE_KEY_NAMES = ['rsa', 'dsa', 'ecdsa', 'ed25519']
KEY_FILE_TPL = '/etc/ssh/ssh_host_%s_key'

CONFIG_KEY_TO_FILE = {}
PRIV_TO_PUB = {}
for k in GENERATE_KEY_NAMES:
    CONFIG_KEY_TO_FILE.update({"%s_private" % k: (KEY_FILE_TPL % k, 0o600)})
    CONFIG_KEY_TO_FILE.update(
        {"%s_public" % k: (KEY_FILE_TPL % k + ".pub", 0o600)})
    PRIV_TO_PUB["%s_private" % k] = "%s_public" % k

KEY_GEN_TPL = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'


def handle(_name, cfg, cloud, log, _args):

    # remove the static keys from the pristine image
    if cfg.get("ssh_deletekeys", True):
        key_pth = os.path.join("/etc/ssh/", "ssh_host_*key*")
        for f in glob.glob(key_pth):
            try:
                util.del_file(f)
            except Exception:
                util.logexc(log, "Failed deleting key file %s", f)

    if "ssh_keys" in cfg:
        # if there are keys in cloud-config, use them
        for (key, val) in cfg["ssh_keys"].items():
            if key in CONFIG_KEY_TO_FILE:
                tgt_fn = CONFIG_KEY_TO_FILE[key][0]
                tgt_perms = CONFIG_KEY_TO_FILE[key][1]
                util.write_file(tgt_fn, val, tgt_perms)

        for (priv, pub) in PRIV_TO_PUB.items():
            if pub in cfg['ssh_keys'] or priv not in cfg['ssh_keys']:
                continue
            pair = (CONFIG_KEY_TO_FILE[priv][0], CONFIG_KEY_TO_FILE[pub][0])
            cmd = ['sh', '-xc', KEY_GEN_TPL % pair]
            try:
                # TODO(harlowja): Is this guard needed?
                with util.SeLinuxGuard("/etc/ssh", recursive=True):
                    util.subp(cmd, capture=False)
                log.debug("Generated a key for %s from %s", pair[0], pair[1])
            except Exception:
                util.logexc(log, "Failed generated a key for %s from %s",
                            pair[0], pair[1])
    else:
        # if not, generate them
        genkeys = util.get_cfg_option_list(cfg,
                                           'ssh_genkeytypes',
                                           GENERATE_KEY_NAMES)
        lang_c = os.environ.copy()
        lang_c['LANG'] = 'C'
        for keytype in genkeys:
            keyfile = KEY_FILE_TPL % (keytype)
            if os.path.exists(keyfile):
                continue
            util.ensure_dir(os.path.dirname(keyfile))
            cmd = ['ssh-keygen', '-t', keytype, '-N', '', '-f', keyfile]

            # TODO(harlowja): Is this guard needed?
            with util.SeLinuxGuard("/etc/ssh", recursive=True):
                try:
                    out, err = util.subp(cmd, capture=True, env=lang_c)
                    sys.stdout.write(util.decode_binary(out))
                except util.ProcessExecutionError as e:
                    err = util.decode_binary(e.stderr).lower()
                    if (e.exit_code == 1 and
                            err.lower().startswith("unknown key")):
                        log.debug("ssh-keygen: unknown key type '%s'", keytype)
                    else:
                        util.logexc(log, "Failed generating key type %s to "
                                    "file %s", keytype, keyfile)

    try:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        disable_root_opts = util.get_cfg_option_str(cfg, "disable_root_opts",
                                                    ssh_util.DISABLE_USER_OPTS)

        keys = cloud.get_public_ssh_keys() or []
        if "ssh_authorized_keys" in cfg:
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys, user, disable_root, disable_root_opts)
    except Exception:
        util.logexc(log, "Applying ssh credentials failed!")


def apply_credentials(keys, user, disable_root, disable_root_opts):

    keys = set(keys)
    if user:
        ssh_util.setup_user_keys(keys, user)

    if disable_root:
        if not user:
            user = "NONE"
        key_prefix = disable_root_opts.replace('$USER', user)
        key_prefix = key_prefix.replace('$DISABLE_USER', 'root')
    else:
        key_prefix = ''

    ssh_util.setup_user_keys(keys, 'root', options=key_prefix)

# vi: ts=4 expandtab
