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


def handle(name, cfg, _cloud, log, _args):
    files = cfg.get('files')
    if not files:
        log.debug(("Skipping module named %s,"
                   " no/empty 'files' key in configuration"), name)
        return
    write_files(name, files, log)


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
        contents = decode_string(f_info.get('content', ''),
                                 f_info.get('compression'))
        (u, g) = util.extract_usergroup(f_info.get('owner'))
        perms = safe_int(f_info.get('permissions'), DEFAULT_PERMS)
        util.write_file(path, contents, mode=perms)
        util.chownbyname(path, u, g)


def safe_int(text, default):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def decode_string(contents, content_type):
    if util.is_true(content_type, addons=['gzip', 'gz']):
        contents_dec = base64.b64decode(contents)
        contents = util.decomp_gzip(contents_dec, quiet=False)
    return contents
