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
import glob
import hashlib
import os

from prettytable import PrettyTable

from cloudinit import util
from cloudinit import ssh_util

FP_HASH_TYPE = 'md5'
FP_SEGMENT_LEN = 2
FP_SEGMENT_SEP = ":"


def _split_hash(bin_hash):
    split_up = []
    for i in xrange(0, len(bin_hash), FP_SEGMENT_LEN):
        split_up.append(bin_hash[i:i+FP_SEGMENT_LEN])
    return split_up


def _gen_fingerprint(b64_text):
    if not b64_text:
        return ''
    # Maybe we should feed this into 'ssh -lf'?
    try:
        bin_text = base64.b64decode(b64_text)
        hasher = hashlib.new(FP_HASH_TYPE)
        hasher.update(bin_text)
        pp_hash = FP_SEGMENT_SEP.join(_split_hash(hasher.hexdigest()))
        return pp_hash
    except TypeError:
        return ''


def _pprint_key_entries(user, key_fn, key_entries, prefix='ci-info: '):
    if not key_entries:
        message = "%sno authorized ssh keys fingerprints found for user %s." % (prefix, user)
        util.multi_log(message)
        return
    tbl_fields = ['Keytype', 'Fingerprint', 'Options', 'Comment']
    tbl = PrettyTable(tbl_fields)
    for entry in key_entries:
        row = []
        row.append(entry.keytype or '-')
        row.append(_gen_fingerprint(entry.base64) or '-')
        row.append(entry.comment or '-')
        row.append(entry.options or '-')
        tbl.add_row(row)
    authtbl_s = tbl.get_string()
    max_len = len(max(authtbl_s.splitlines(), key=len))
    lines = [
        util.center("Authorized keys fingerprints from %s for user %s" % (key_fn, user), "+", max_len),
    ]
    lines.extend(authtbl_s.splitlines())
    for line in lines:
        util.multi_log(text="%s%s\n" % (prefix, line))


def handle(name, cfg, cloud, log, _args):
    if 'no_ssh_fingerprints' in cfg:
        log.debug(("Skipping module named %s, "
                   "logging of ssh fingerprints disabled"), name)

    user = util.get_cfg_option_str(cfg, "user", "ubuntu")
    (auth_key_fn, auth_key_entries) = ssh_util.extract_authorized_keys(user, cloud.paths)
    _pprint_key_entries(user, auth_key_fn, auth_key_entries)
