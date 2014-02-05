# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Yahoo! Inc.
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
from StringIO import StringIO

from cloudinit.settings import PER_INSTANCE
from cloudinit import util

frequency = PER_INSTANCE


def _decode(data, encoding=None):
    if not data:
        return ''
    if not encoding or encoding.lower() in ['raw']:
        return data
    elif encoding.lower() in ['base64', 'b64']:
        return base64.b64decode(data)
    elif encoding.lower() in ['gzip', 'gz']:
        return util.decomp_gzip(data, quiet=False)
    else:
        raise IOError("Unknown random_seed encoding: %s" % (encoding))


def handle(name, cfg, cloud, log, _args):
    if not cfg or "random_seed" not in cfg:
        log.debug(("Skipping module named %s, "
                   "no 'random_seed' configuration found"), name)
        return

    my_cfg = cfg['random_seed']
    seed_path = my_cfg.get('file', '/dev/urandom')
    seed_buf = StringIO()
    seed_buf.write(_decode(my_cfg.get('data', ''),
                           encoding=my_cfg.get('encoding')))

    metadata = cloud.datasource.metadata
    if metadata and 'random_seed' in metadata:
        seed_buf.write(metadata['random_seed'])

    seed_data = seed_buf.getvalue()
    if len(seed_data):
        log.debug("%s: adding %s bytes of random seed entrophy to %s", name,
                  len(seed_data), seed_path)
        util.append_file(seed_path, seed_data)
