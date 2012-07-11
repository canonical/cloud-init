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
import os

from cloudinit import util
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

DEFAULT_PERMS = 0644
UNKNOWN_ENC = 'text/plain'


def handle(name, cfg, _cloud, log, _args):
    files = cfg.get('write_files')
    if not files:
        log.debug(("Skipping module named %s,"
                   " no/empty 'files' key in configuration"), name)
        return
    write_files(name, files, log)


def canonicalize_decoding(enc):
    if not enc:
        enc = ''
    enc = enc.lower().strip()
    # Translate to a mime-type (or set of) that will be understood
    # when decoding (for now we only support a limited set of known mime-types)
    # See: http://tiny.cc/m4kahw
    # See: http://www.iana.org/assignments/media-types/index.html
    if enc in ['gz', 'gzip']:
        # Should we assume that this is 'always' base64?
        # Someone might of got lucky and not had to encode it?
        return ['application/x-gzip']
    if enc in ['gz+base64', 'gzip+base64', 'gz+b64', 'gzip+b64']:
        return ['application/base64', 'application/x-gzip']
    if enc in ['base64', 'b64']:
        return ['application/base64']
    if enc in ['base32', 'b32']:
        return ['application/base32']
    if enc in ['base16', 'b16']:
        return ['application/base16']
    return [UNKNOWN_ENC]


def write_files(name, files, log):
    if not files:
        return

    for (i, f_info) in enumerate(files):
        path = f_info.get('path')
        if not path:
            log.warn("No path provided to write for entry %s in module %s",
                     i + 1, name)
            continue
        path = os.path.abspath(path)
        decodings = canonicalize_decoding(f_info.get('encoding'))
        contents = decode_contents(f_info.get('content', ''), decodings)
        (u, g) = util.extract_usergroup(f_info.get('owner'))
        perms = safe_int(f_info.get('permissions'), DEFAULT_PERMS)
        util.write_file(path, contents, mode=perms)
        util.chownbyname(path, u, g)


def safe_int(text, default):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def decode_contents(contents, decodings):
    result = str(contents)
    for enc in decodings:
        if enc == 'application/x-gzip':
            result = util.decomp_gzip(result, quiet=False)
        elif enc == 'application/base64':
            result = base64.b64decode(result)
        elif enc == 'application/base32':
            result = base64.b32decode(result)
        elif enc == 'application/base16':
            result = base64.b16decode(result)
        elif enc == UNKNOWN_ENC:
            pass
    return result
