# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
SSH Authkey Fingerprints
------------------------
**Summary:** log fingerprints of user ssh keys

Write fingerprints of authorized keys for each user to log. This is enabled by
default, but can be disabled using ``no_ssh_fingerprints``. The hash type for
the keys can be specified, but defaults to ``md5``.

**Internal name:** `` cc_ssh_authkey_fingerprints``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    no_ssh_fingerprints: <true/false>
    authkey_hash: <hash type>
"""

import base64
import hashlib

from prettytable import PrettyTable

from cloudinit.distros import ug_util
from cloudinit import ssh_util
from cloudinit import util


def _split_hash(bin_hash):
    split_up = []
    for i in range(0, len(bin_hash), 2):
        split_up.append(bin_hash[i:i + 2])
    return split_up


def _gen_fingerprint(b64_text, hash_meth='md5'):
    if not b64_text:
        return ''
    # TBD(harlowja): Maybe we should feed this into 'ssh -lf'?
    try:
        hasher = hashlib.new(hash_meth)
        hasher.update(base64.b64decode(b64_text))
        return ":".join(_split_hash(hasher.hexdigest()))
    except (TypeError, ValueError):
        # Raised when b64 not really b64...
        # or when the hash type is not really
        # a known/supported hash type...
        return '?'


def _is_printable_key(entry):
    if any([entry.keytype, entry.base64, entry.comment, entry.options]):
        if (entry.keytype and
                entry.keytype.lower().strip() in ['ssh-dss', 'ssh-rsa']):
            return True
    return False


def _pprint_key_entries(user, key_fn, key_entries, hash_meth='md5',
                        prefix='ci-info: '):
    if not key_entries:
        message = ("%sno authorized ssh keys fingerprints found for user %s.\n"
                   % (prefix, user))
        util.multi_log(message)
        return
    tbl_fields = ['Keytype', 'Fingerprint (%s)' % (hash_meth), 'Options',
                  'Comment']
    tbl = PrettyTable(tbl_fields)
    for entry in key_entries:
        if _is_printable_key(entry):
            row = []
            row.append(entry.keytype or '-')
            row.append(_gen_fingerprint(entry.base64, hash_meth) or '-')
            row.append(entry.options or '-')
            row.append(entry.comment or '-')
            tbl.add_row(row)
    authtbl_s = tbl.get_string()
    authtbl_lines = authtbl_s.splitlines()
    max_len = len(max(authtbl_lines, key=len))
    lines = [
        util.center("Authorized keys from %s for user %s" %
                    (key_fn, user), "+", max_len),
    ]
    lines.extend(authtbl_lines)
    for line in lines:
        util.multi_log(text="%s%s\n" % (prefix, line),
                       stderr=False, console=True)


def handle(name, cfg, cloud, log, _args):
    if util.is_true(cfg.get('no_ssh_fingerprints', False)):
        log.debug(("Skipping module named %s, "
                   "logging of ssh fingerprints disabled"), name)
        return

    hash_meth = util.get_cfg_option_str(cfg, "authkey_hash", "md5")
    (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    for (user_name, _cfg) in users.items():
        (key_fn, key_entries) = ssh_util.extract_authorized_keys(user_name)
        _pprint_key_entries(user_name, key_fn,
                            key_entries, hash_meth)

# vi: ts=4 expandtab
