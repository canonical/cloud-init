# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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

import base64
import hashlib

from prettytable import PrettyTable

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit import distros as ds

from cloudinit import ssh_util
from cloudinit import util


def _split_hash(bin_hash):
    split_up = []
    for i in xrange(0, len(bin_hash), 2):
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
    (users, _groups) = ds.normalize_users_groups(cfg, cloud.distro)
    for (user_name, _cfg) in users.items():
        (key_fn, key_entries) = ssh_util.extract_authorized_keys(user_name)
        _pprint_key_entries(user_name, key_fn,
                            key_entries, hash_meth)
