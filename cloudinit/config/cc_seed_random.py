# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Yahoo! Inc.
#    Copyright (C) 2014 Canonical, Ltd
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Dustin Kirkland <kirkland@ubuntu.com>
#    Author: Scott Moser <scott.moser@canonical.com>
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
from StringIO import StringIO

from cloudinit.settings import PER_INSTANCE
from cloudinit import log as logging
from cloudinit import util

frequency = PER_INSTANCE
LOG = logging.getLogger(__name__)


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


def handle_random_seed_command(command, required, env=None):
    if not command and required:
        raise ValueError("no command found but required=true")
    elif not command:
        LOG.debug("no command provided")
        return

    cmd = command[0]
    if not util.which(cmd):
        if required:
            raise ValueError("command '%s' not found but required=true", cmd)
        else:
            LOG.debug("command '%s' not found for seed_command", cmd)
            return
    util.subp(command, env=env, capture=False)


def handle(name, cfg, cloud, log, _args):
    mycfg = cfg.get('random_seed', {})
    seed_path = mycfg.get('file', '/dev/urandom')
    seed_data = mycfg.get('data', '')

    seed_buf = StringIO()
    if seed_data:
        seed_buf.write(_decode(seed_data, encoding=mycfg.get('encoding')))

    # 'random_seed' is set up by Azure datasource, and comes already in
    # openstack meta_data.json
    metadata = cloud.datasource.metadata
    if metadata and 'random_seed' in metadata:
        seed_buf.write(metadata['random_seed'])

    seed_data = seed_buf.getvalue()
    if len(seed_data):
        log.debug("%s: adding %s bytes of random seed entropy to %s", name,
                  len(seed_data), seed_path)
        util.append_file(seed_path, seed_data)

    command = mycfg.get('command', ['pollinate', '-q'])
    req = mycfg.get('command_required', False)
    try:
        env = os.environ.copy()
        env['RANDOM_SEED_FILE'] = seed_path
        handle_random_seed_command(command=command, required=req, env=env)
    except ValueError as e:
        log.warn("handling random command [%s] failed: %s", command, e)
        raise e
