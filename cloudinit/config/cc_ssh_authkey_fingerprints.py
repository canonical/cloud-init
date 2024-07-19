# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""SSH AuthKey Fingerprints: Log fingerprints of user SSH keys"""

import base64
import hashlib
import logging

from cloudinit import ssh_util, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, ug_util
from cloudinit.settings import PER_INSTANCE
from cloudinit.simpletable import SimpleTable

meta: MetaSchema = {
    "id": "cc_ssh_authkey_fingerprints",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type:ignore

LOG = logging.getLogger(__name__)


def _split_hash(bin_hash):
    split_up = []
    for i in range(0, len(bin_hash), 2):
        split_up.append(bin_hash[i : i + 2])
    return split_up


def _gen_fingerprint(b64_text, hash_meth="sha256"):
    if not b64_text:
        return ""
    # TBD(harlowja): Maybe we should feed this into 'ssh -lf'?
    try:
        hasher = hashlib.new(hash_meth)
        hasher.update(base64.b64decode(b64_text))
        return ":".join(_split_hash(hasher.hexdigest()))
    except (TypeError, ValueError):
        # Raised when b64 not really b64...
        # or when the hash type is not really
        # a known/supported hash type...
        return "?"


def _is_printable_key(entry):
    if any([entry.keytype, entry.base64, entry.comment, entry.options]):
        if (
            entry.keytype
            and entry.keytype.lower().strip() in ssh_util.VALID_KEY_TYPES
        ):
            return True
    return False


def _pprint_key_entries(
    user, key_fn, key_entries, hash_meth="sha256", prefix="ci-info: "
):
    if not key_entries:
        message = (
            "%sno authorized SSH keys fingerprints found for user %s.\n"
            % (prefix, user)
        )
        util.multi_log(message, console=True, stderr=False)
        return
    tbl_fields = [
        "Keytype",
        "Fingerprint (%s)" % (hash_meth),
        "Options",
        "Comment",
    ]
    tbl = SimpleTable(tbl_fields)
    for entry in key_entries:
        if _is_printable_key(entry):
            row = [
                entry.keytype or "-",
                _gen_fingerprint(entry.base64, hash_meth) or "-",
                entry.options or "-",
                entry.comment or "-",
            ]
            tbl.add_row(row)
    authtbl_s = tbl.get_string()
    authtbl_lines = authtbl_s.splitlines()
    max_len = len(max(authtbl_lines, key=len))
    lines = [
        util.center(
            "Authorized keys from %s for user %s" % (key_fn, user),
            "+",
            max_len,
        ),
    ]
    lines.extend(authtbl_lines)
    for line in lines:
        util.multi_log(
            text="%s%s\n" % (prefix, line), stderr=False, console=True
        )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if util.is_true(cfg.get("no_ssh_fingerprints", False)):
        LOG.debug(
            "Skipping module named %s, logging of SSH fingerprints disabled",
            name,
        )
        return

    hash_meth = util.get_cfg_option_str(cfg, "authkey_hash", "sha256")
    (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    for (user_name, _cfg) in users.items():
        if _cfg.get("no_create_home") or _cfg.get("system"):
            LOG.debug(
                "Skipping printing of ssh fingerprints for user '%s' because "
                "no home directory is created",
                user_name,
            )
            continue

        (key_fn, key_entries) = ssh_util.extract_authorized_keys(user_name)
        _pprint_key_entries(user_name, key_fn, key_entries, hash_meth)
