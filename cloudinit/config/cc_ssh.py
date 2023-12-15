# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""SSH: Configure SSH and SSH keys"""

import glob
import logging
import os
import re
import sys
from textwrap import dedent
from typing import List, Optional, Sequence

from cloudinit import ssh_util, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, ug_util
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module handles most configuration for SSH and both host and authorized SSH
keys.

**Authorized keys**

Authorized keys are a list of public SSH keys that are allowed to connect to
a user account on a system. They are stored in `.ssh/authorized_keys` in that
account's home directory. Authorized keys for the default user defined in
``users`` can be specified using ``ssh_authorized_keys``. Keys
should be specified as a list of public keys.

.. note::
    See the ``cc_set_passwords`` module documentation to enable/disable SSH
    password authentication.

Root login can be enabled/disabled using the ``disable_root`` config key. Root
login options can be manually specified with ``disable_root_opts``.

Supported public key types for the ``ssh_authorized_keys`` are:

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

    ``rsa``, ``ecdsa`` and ``ed25519`` are added for legacy,
    as they are valid public keys in some old distros. They can possibly
    be removed in the future when support for the older distros are dropped

.. _OpenSSH: https://github.com/openssh/openssh-portable/blob/master/sshkey.c

**Host keys**

Host keys are for authenticating a specific instance. Many images have default
host SSH keys, which can be removed using ``ssh_deletekeys``.

Host keys can be added using the ``ssh_keys`` configuration key.

When host keys are generated the output of the ssh-keygen command(s) can be
displayed on the console using the ``ssh_quiet_keygen`` configuration key.

.. note::
    When specifying private host keys in cloud-config, care should be taken to
    ensure that the communication between the data source and the instance is
    secure.


If no host keys are specified using ``ssh_keys``, then keys will be generated
using ``ssh-keygen``. By default one public/private pair of each supported
host key type will be generated. The key types to generate can be specified
using the ``ssh_genkeytypes`` config flag, which accepts a list of host key
types to use. For each host key type for which this module has been instructed
to create a keypair, if a key of the same type is already present on the
system (i.e. if ``ssh_deletekeys`` was false), no key will be generated.

Supported host key types for the ``ssh_keys`` and the ``ssh_genkeytypes``
config flags are:

    - ecdsa
    - ed25519
    - rsa

Unsupported host key types for the ``ssh_keys`` and the ``ssh_genkeytypes``
config flags are:

    - ecdsa-sk
    - ed25519-sk
"""

# Note: We do not support *-sk key types because:
# 1) In the autogeneration case user interaction with the device is needed
# which does not fit with a cloud-context.
# 2) This type of keys are user-based, not hostkeys.


meta: MetaSchema = {
    "id": "cc_ssh",
    "name": "SSH",
    "title": "Configure SSH and SSH keys",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            ssh_keys:
              rsa_private: |
                -----BEGIN RSA PRIVATE KEY-----
                MIIBxwIBAAJhAKD0YSHy73nUgysO13XsJmd4fHiFyQ+00R7VVu2iV9Qco
                ...
                -----END RSA PRIVATE KEY-----
              rsa_public: ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEAoPRhIfLvedSDKw7Xd ...
              rsa_certificate: |
                ssh-rsa-cert-v01@openssh.com AAAAIHNzaC1lZDI1NTE5LWNlcnQt ...
            ssh_authorized_keys:
              - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEA3FSyQwBI6Z+nCSjUU ...
              - ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZ ...
            ssh_deletekeys: true
            ssh_genkeytypes: [rsa, ecdsa, ed25519]
            disable_root: true
            disable_root_opts: no-port-forwarding,no-agent-forwarding,no-X11-forwarding
            allow_public_ssh_keys: true
            ssh_quiet_keygen: true
            ssh_publish_hostkeys:
              enabled: true
              blacklist: [rsa]
            """  # noqa: E501
        )
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)
LOG = logging.getLogger(__name__)

GENERATE_KEY_NAMES = ["rsa", "ecdsa", "ed25519"]
FIPS_UNSUPPORTED_KEY_NAMES = ["ed25519"]

pattern_unsupported_config_keys = re.compile(
    "^(ecdsa-sk|ed25519-sk)_(private|public|certificate)$"
)
KEY_FILE_TPL = "/etc/ssh/ssh_host_%s_key"
PUBLISH_HOST_KEYS = True
# By default publish all supported hostkey types.
HOST_KEY_PUBLISH_BLACKLIST: List[str] = []

CONFIG_KEY_TO_FILE = {}
PRIV_TO_PUB = {}
for k in GENERATE_KEY_NAMES:
    CONFIG_KEY_TO_FILE.update(
        {
            f"{k}_private": (KEY_FILE_TPL % k, 0o600),
            f"{k}_public": (f"{KEY_FILE_TPL % k}.pub", 0o644),
            f"{k}_certificate": (f"{KEY_FILE_TPL % k}-cert.pub", 0o644),
        }
    )
    PRIV_TO_PUB[f"{k}_private"] = f"{k}_public"

KEY_GEN_TPL = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:

    # remove the static keys from the pristine image
    if cfg.get("ssh_deletekeys", True):
        key_pth = os.path.join("/etc/ssh/", "ssh_host_*key*")
        for f in glob.glob(key_pth):
            try:
                util.del_file(f)
            except Exception:
                util.logexc(LOG, "Failed deleting key file %s", f)

    if "ssh_keys" in cfg:
        # if there are keys and/or certificates in cloud-config, use them
        cert_config = []
        for (key, val) in cfg["ssh_keys"].items():
            if key not in CONFIG_KEY_TO_FILE:
                if pattern_unsupported_config_keys.match(key):
                    reason = "unsupported"
                else:
                    reason = "unrecognized"
                LOG.warning('Skipping %s ssh_keys entry: "%s"', reason, key)
                continue
            tgt_fn = CONFIG_KEY_TO_FILE[key][0]
            tgt_perms = CONFIG_KEY_TO_FILE[key][1]
            util.write_file(tgt_fn, val, tgt_perms)
            # set server to present the most recently identified certificate
            if "_certificate" in key:
                cert_config.append(("HostCertificate", str(tgt_fn)))

        if cert_config:
            ssh_util.append_ssh_config(cert_config)

        for private_type, public_type in PRIV_TO_PUB.items():
            if (
                public_type in cfg["ssh_keys"]
                or private_type not in cfg["ssh_keys"]
            ):
                continue
            private_file, public_file = (
                CONFIG_KEY_TO_FILE[private_type][0],
                CONFIG_KEY_TO_FILE[public_type][0],
            )
            cmd = ["sh", "-xc", KEY_GEN_TPL % (private_file, public_file)]
            try:
                # TODO(harlowja): Is this guard needed?
                with util.SeLinuxGuard("/etc/ssh", recursive=True):
                    subp.subp(cmd, capture=False)
                LOG.debug(
                    "Generated a key for %s from %s", public_file, private_file
                )
            except Exception:
                util.logexc(
                    LOG,
                    "Failed generating a key for "
                    f"{public_file} from {private_file}",
                )
    else:
        # if not, generate them
        genkeys = util.get_cfg_option_list(
            cfg, "ssh_genkeytypes", GENERATE_KEY_NAMES
        )
        # remove keys that are not supported in fips mode if its enabled
        key_names = (
            genkeys
            if not util.fips_enabled()
            else [
                names
                for names in genkeys
                if names not in FIPS_UNSUPPORTED_KEY_NAMES
            ]
        )
        skipped_keys = set(genkeys).difference(key_names)
        if skipped_keys:
            LOG.debug(
                "skipping keys that are not supported in fips mode: %s",
                ",".join(skipped_keys),
            )

        for keytype in key_names:
            keyfile = KEY_FILE_TPL % (keytype)
            if os.path.exists(keyfile):
                continue
            util.ensure_dir(os.path.dirname(keyfile))
            cmd = ["ssh-keygen", "-t", keytype, "-N", "", "-f", keyfile]

            # TODO(harlowja): Is this guard needed?
            with util.SeLinuxGuard("/etc/ssh", recursive=True):
                try:
                    out, err = subp.subp(
                        cmd, capture=True, update_env={"LANG": "C"}
                    )
                    if not util.get_cfg_option_bool(
                        cfg, "ssh_quiet_keygen", False
                    ):
                        sys.stdout.write(util.decode_binary(out))

                    gid = util.get_group_id("ssh_keys")
                    if gid != -1:
                        # perform same "sanitize permissions" as sshd-keygen
                        permissions_private = 0o600
                        ssh_version = ssh_util.get_opensshd_upstream_version()
                        if ssh_version and ssh_version < util.Version(9, 0):
                            permissions_private = 0o640
                        os.chown(keyfile, -1, gid)
                        os.chmod(keyfile, permissions_private)
                        os.chmod(f"{keyfile}.pub", 0o644)
                except subp.ProcessExecutionError as e:
                    err = util.decode_binary(e.stderr).lower()
                    if e.exit_code == 1 and err.lower().startswith(
                        "unknown key"
                    ):
                        LOG.debug("ssh-keygen: unknown key type '%s'", keytype)
                    else:
                        util.logexc(
                            LOG,
                            "Failed generating key type %s to file %s",
                            keytype,
                            keyfile,
                        )

    if "ssh_publish_hostkeys" in cfg:
        host_key_blacklist = util.get_cfg_option_list(
            cfg["ssh_publish_hostkeys"],
            "blacklist",
            HOST_KEY_PUBLISH_BLACKLIST,
        )
        publish_hostkeys = util.get_cfg_option_bool(
            cfg["ssh_publish_hostkeys"], "enabled", PUBLISH_HOST_KEYS
        )
    else:
        host_key_blacklist = HOST_KEY_PUBLISH_BLACKLIST
        publish_hostkeys = PUBLISH_HOST_KEYS

    if publish_hostkeys:
        hostkeys = get_public_host_keys(blacklist=host_key_blacklist)
        try:
            cloud.datasource.publish_host_keys(hostkeys)
        except Exception:
            util.logexc(LOG, "Publishing host keys failed!")

    try:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        disable_root_opts = util.get_cfg_option_str(
            cfg, "disable_root_opts", ssh_util.DISABLE_USER_OPTS
        )

        keys: List[str] = []
        if util.get_cfg_option_bool(cfg, "allow_public_ssh_keys", True):
            keys = cloud.get_public_ssh_keys() or []
        else:
            LOG.debug(
                "Skipping import of publish SSH keys per "
                "config setting: allow_public_ssh_keys=False"
            )

        if "ssh_authorized_keys" in cfg:
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys, user, disable_root, disable_root_opts)
    except Exception:
        util.logexc(LOG, "Applying SSH credentials failed!")


def apply_credentials(keys, user, disable_root, disable_root_opts):

    keys = set(keys)
    if user:
        ssh_util.setup_user_keys(keys, user)

    if disable_root:
        if not user:
            user = "NONE"
        key_prefix = disable_root_opts.replace("$USER", user)
        key_prefix = key_prefix.replace("$DISABLE_USER", "root")
    else:
        key_prefix = ""

    ssh_util.setup_user_keys(keys, "root", options=key_prefix)


def get_public_host_keys(blacklist: Optional[Sequence[str]] = None):
    """Read host keys from /etc/ssh/*.pub files and return them as a list.

    @param blacklist: List of key types to ignore. e.g. ['rsa']
    @returns: List of keys, each formatted as a two-element tuple.
        e.g. [('ssh-rsa', 'AAAAB3Nz...'), ('ssh-ed25519', 'AAAAC3Nx...')]
    """
    public_key_file_tmpl = "%s.pub" % (KEY_FILE_TPL,)
    key_list = []
    blacklist_files = []
    if blacklist:
        # Convert blacklist to filenames:
        # 'rsa' -> '/etc/ssh/ssh_host_rsa_key.pub'
        blacklist_files = [
            public_key_file_tmpl % (key_type,) for key_type in blacklist
        ]
    # Get list of public key files and filter out blacklisted files.
    file_list = [
        hostfile
        for hostfile in glob.glob(public_key_file_tmpl % ("*",))
        if hostfile not in blacklist_files
    ]

    # Read host key files, retrieve first two fields as a tuple and
    # append that tuple to key_list.
    for file_name in file_list:
        file_contents = util.load_file(file_name)
        key_data = file_contents.split()
        if key_data and len(key_data) > 1:
            key_list.append(tuple(key_data[:2]))
    return key_list
