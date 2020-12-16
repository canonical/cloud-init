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
**Summary:** configure SSH and SSH keys (host and authorized)

This module handles most configuration for SSH and both host and authorized SSH
keys.

Authorized Keys
^^^^^^^^^^^^^^^

Authorized keys are a list of public SSH keys that are allowed to connect to a
a user account on a system. They are stored in `.ssh/authorized_keys` in that
account's home directory. Authorized keys for the default user defined in
``users`` can be specified using ``ssh_authorized_keys``. Keys
should be specified as a list of public keys.

.. note::
    see the ``cc_set_passwords`` module documentation to enable/disable SSH
    password authentication

Root login can be enabled/disabled using the ``disable_root`` config key. Root
login options can be manually specified with ``disable_root_opts``. If
``disable_root_opts`` is specified and contains the string ``$USER``,
it will be replaced with the username of the default user. By default,
root login is disabled, and root login opts are set to::

    no-port-forwarding,no-agent-forwarding,no-X11-forwarding

Supported public key types for the ``ssh_authorized_keys`` are:

    - dsa
    - rsa
    - ecdsa
    - ed25519
    - ecdsa-sha2-nistp256-cert-v01@openssh.com
    - ecdsa-sha2-nistp256
    - ecdsa-sha2-nistp384-cert-v01@openssh.com
    - ecdsa-sha2-nistp384
    - ecdsa-sha2-nistp521-cert-v01@openssh.com
    - ecdsa-sha2-nistp521
    - sk-ecdsa-sha2-nistp256-cert-v01@openssh.com
    - sk-ecdsa-sha2-nistp256@openssh.com
    - sk-ssh-ed25519-cert-v01@openssh.com
    - sk-ssh-ed25519@openssh.com
    - ssh-dss-cert-v01@openssh.com
    - ssh-dss
    - ssh-ed25519-cert-v01@openssh.com
    - ssh-ed25519
    - ssh-rsa-cert-v01@openssh.com
    - ssh-rsa
    - ssh-xmss-cert-v01@openssh.com
    - ssh-xmss@openssh.com

.. note::
    this list has been filtered out from the supported keytypes of
    `OpenSSH`_ source, where the sigonly keys are removed. Please see
    ``ssh_util`` for more information.

    ``dsa``, ``rsa``, ``ecdsa`` and ``ed25519`` are added for legacy,
    as they are valid public keys in some old distros. They can possibly
    be removed in the future when support for the older distros are dropped

.. _OpenSSH: https://github.com/openssh/openssh-portable/blob/master/sshkey.c

Host Keys
^^^^^^^^^

Host keys are for authenticating a specific instance. Many images have default
host SSH keys, which can be removed using ``ssh_deletekeys``. This prevents
re-use of a private host key from an image on multiple machines. Since
removing default host keys is usually the desired behavior this option is
enabled by default.

Host keys can be added using the ``ssh_keys`` configuration key. The argument
to this config key should be a dictionary entries for the public and private
keys of each desired key type. Entries in the ``ssh_keys`` config dict should
have keys in the format ``<key type>_private``, ``<key type>_public``, and,
optionally, ``<key type>_certificate``, e.g. ``rsa_private: <key>``,
``rsa_public: <key>``, and ``rsa_certificate: <key>``. See below for supported
key types. Not all key types have to be specified, ones left unspecified will
not be used. If this config option is used, then no keys will be generated.

.. note::
    when specifying private host keys in cloud-config, care should be taken to
    ensure that the communication between the data source and the instance is
    secure

.. note::
    to specify multiline private host keys and certificates, use yaml
    multiline syntax

If no host keys are specified using ``ssh_keys``, then keys will be generated
using ``ssh-keygen``. By default one public/private pair of each supported
host key type will be generated. The key types to generate can be specified
using the ``ssh_genkeytypes`` config flag, which accepts a list of host key
types to use. For each host key type for which this module has been instructed
to create a keypair, if a key of the same type is already present on the
system (i.e. if ``ssh_deletekeys`` was false), no key will be generated.

Supported host key types for the ``ssh_keys`` and the ``ssh_genkeytypes``
config flags are:

    - rsa
    - dsa
    - ecdsa
    - ed25519

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
        rsa_certificate: |
            ssh-rsa-cert-v01@openssh.com AAAAIHNzaC1lZDI1NTE5LWNlcnQt ...
        dsa_private: |
            -----BEGIN DSA PRIVATE KEY-----
            MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+00R7VVu2iV9Qco
            ...
            -----END DSA PRIVATE KEY-----
        dsa_public: ssh-dsa AAAAB3NzaC1yc2EAAAABIwAAAGEAoPRhIfLvedSDKw7Xd ...
        dsa_certificate: |
            ssh-dsa-cert-v01@openssh.com AAAAIHNzaC1lZDI1NTE5LWNlcnQt ...

    ssh_genkeytypes: <key type>
    disable_root: <true/false>
    disable_root_opts: <disable root options string>
    ssh_authorized_keys:
        - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEA3FSyQwBI6Z+nCSjUU ...
        - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZ ...
    allow_public_ssh_keys: <true/false>
    ssh_publish_hostkeys:
        enabled: <true/false> (Defaults to true)
        blacklist: <list of key types> (Defaults to [dsa])
"""

import glob
import os
import sys

from cloudinit.distros import ug_util
from cloudinit import ssh_util
from cloudinit import subp
from cloudinit import util


GENERATE_KEY_NAMES = ['rsa', 'dsa', 'ecdsa', 'ed25519']
KEY_FILE_TPL = '/etc/ssh/ssh_host_%s_key'
PUBLISH_HOST_KEYS = True
# Don't publish the dsa hostkey by default since OpenSSH recommends not using
# it.
HOST_KEY_PUBLISH_BLACKLIST = ['dsa']

CONFIG_KEY_TO_FILE = {}
PRIV_TO_PUB = {}
for k in GENERATE_KEY_NAMES:
    CONFIG_KEY_TO_FILE.update({"%s_private" % k: (KEY_FILE_TPL % k, 0o600)})
    CONFIG_KEY_TO_FILE.update(
        {"%s_public" % k: (KEY_FILE_TPL % k + ".pub", 0o600)})
    CONFIG_KEY_TO_FILE.update(
        {"%s_certificate" % k: (KEY_FILE_TPL % k + "-cert.pub", 0o600)})
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
        # if there are keys and/or certificates in cloud-config, use them
        for (key, val) in cfg["ssh_keys"].items():
            # skip entry if unrecognized
            if key not in CONFIG_KEY_TO_FILE:
                continue
            tgt_fn = CONFIG_KEY_TO_FILE[key][0]
            tgt_perms = CONFIG_KEY_TO_FILE[key][1]
            util.write_file(tgt_fn, val, tgt_perms)
            # set server to present the most recently identified certificate
            if '_certificate' in key:
                cert_config = {'HostCertificate': tgt_fn}
                ssh_util.update_ssh_config(cert_config)

        for (priv, pub) in PRIV_TO_PUB.items():
            if pub in cfg['ssh_keys'] or priv not in cfg['ssh_keys']:
                continue
            pair = (CONFIG_KEY_TO_FILE[priv][0], CONFIG_KEY_TO_FILE[pub][0])
            cmd = ['sh', '-xc', KEY_GEN_TPL % pair]
            try:
                # TODO(harlowja): Is this guard needed?
                with util.SeLinuxGuard("/etc/ssh", recursive=True):
                    subp.subp(cmd, capture=False)
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
                    out, err = subp.subp(cmd, capture=True, env=lang_c)
                    sys.stdout.write(util.decode_binary(out))
                except subp.ProcessExecutionError as e:
                    err = util.decode_binary(e.stderr).lower()
                    if (e.exit_code == 1 and
                            err.lower().startswith("unknown key")):
                        log.debug("ssh-keygen: unknown key type '%s'", keytype)
                    else:
                        util.logexc(log, "Failed generating key type %s to "
                                    "file %s", keytype, keyfile)

    if "ssh_publish_hostkeys" in cfg:
        host_key_blacklist = util.get_cfg_option_list(
            cfg["ssh_publish_hostkeys"], "blacklist",
            HOST_KEY_PUBLISH_BLACKLIST)
        publish_hostkeys = util.get_cfg_option_bool(
            cfg["ssh_publish_hostkeys"], "enabled", PUBLISH_HOST_KEYS)
    else:
        host_key_blacklist = HOST_KEY_PUBLISH_BLACKLIST
        publish_hostkeys = PUBLISH_HOST_KEYS

    if publish_hostkeys:
        hostkeys = get_public_host_keys(blacklist=host_key_blacklist)
        try:
            cloud.datasource.publish_host_keys(hostkeys)
        except Exception:
            util.logexc(log, "Publishing host keys failed!")

    try:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        disable_root_opts = util.get_cfg_option_str(cfg, "disable_root_opts",
                                                    ssh_util.DISABLE_USER_OPTS)

        keys = []
        if util.get_cfg_option_bool(cfg, 'allow_public_ssh_keys', True):
            keys = cloud.get_public_ssh_keys() or []
        else:
            log.debug('Skipping import of publish SSH keys per '
                      'config setting: allow_public_ssh_keys=False')

        if "ssh_authorized_keys" in cfg:
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys, user, disable_root, disable_root_opts)
    except Exception:
        util.logexc(log, "Applying SSH credentials failed!")


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


def get_public_host_keys(blacklist=None):
    """Read host keys from /etc/ssh/*.pub files and return them as a list.

    @param blacklist: List of key types to ignore. e.g. ['dsa', 'rsa']
    @returns: List of keys, each formatted as a two-element tuple.
        e.g. [('ssh-rsa', 'AAAAB3Nz...'), ('ssh-ed25519', 'AAAAC3Nx...')]
    """
    public_key_file_tmpl = '%s.pub' % (KEY_FILE_TPL,)
    key_list = []
    blacklist_files = []
    if blacklist:
        # Convert blacklist to filenames:
        # 'dsa' -> '/etc/ssh/ssh_host_dsa_key.pub'
        blacklist_files = [public_key_file_tmpl % (key_type,)
                           for key_type in blacklist]
    # Get list of public key files and filter out blacklisted files.
    file_list = [hostfile for hostfile
                 in glob.glob(public_key_file_tmpl % ('*',))
                 if hostfile not in blacklist_files]

    # Read host key files, retrieve first two fields as a tuple and
    # append that tuple to key_list.
    for file_name in file_list:
        file_contents = util.load_file(file_name)
        key_data = file_contents.split()
        if key_data and len(key_data) > 1:
            key_list.append(tuple(key_data[:2]))
    return key_list


# vi: ts=4 expandtab
