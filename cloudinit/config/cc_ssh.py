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
from typing import List, Optional, Sequence

from cloudinit import ssh_util, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, ug_util
from cloudinit.settings import PER_INSTANCE

# Note: We do not support *-sk key types because:
# 1) In the autogeneration case user interaction with the device is needed
# which does not fit with a cloud-context.
# 2) This type of keys are user-based, not hostkeys.

meta: MetaSchema = {
    "id": "cc_ssh",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type:ignore

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


def set_redhat_keyfile_perms(keyfile: str) -> None:
    """
    For fedora 37, centos 9 stream and below:
     - sshd version is earlier than version 9.
     - 'ssh_keys' group is present and owns the private keys.
     - private keys have permission 0o640.
    For fedora 38, centos 10 stream and above:
     - ssh version is atleast version 9.
     - 'ssh_keys' group is absent. 'root' group owns the keys.
     - private keys have permission 0o600, same as upstream.
    Public keys in all cases have permission 0o644.
    """
    permissions_public = 0o644
    ssh_version = ssh_util.get_opensshd_upstream_version()
    if ssh_version and ssh_version < util.Version(9, 0):
        # fedora 37, centos 9 stream and below has sshd
        # versions less than 9 and private key permissions are
        # set to 0o640 from sshd-keygen.
        # See sanitize permissions" section in sshd-keygen.
        permissions_private = 0o640
    else:
        # fedora 38, centos 10 stream and above. sshd-keygen sets
        # private key persmissions to 0o600.
        permissions_private = 0o600

    gid = util.get_group_id("ssh_keys")
    if gid != -1:
        # 'ssh_keys' group exists for fedora 37, centos 9 stream
        # and below. On these distros, 'ssh_keys' group own the private
        # keys. When 'ssh_keys' group is absent for newer distros,
        # 'root' group owns the private keys which is the default.
        os.chown(keyfile, -1, gid)
    os.chmod(keyfile, permissions_private)
    os.chmod(f"{keyfile}.pub", permissions_public)


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

                    if cloud.distro.osfamily == "redhat":
                        set_redhat_keyfile_perms(keyfile)
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
        file_contents = util.load_text_file(file_name)
        key_data = file_contents.split()
        if key_data and len(key_data) > 1:
            key_list.append(tuple(key_data[:2]))
    return key_list
