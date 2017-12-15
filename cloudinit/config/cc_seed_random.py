# Copyright (C) 2013 Yahoo! Inc.
# Copyright (C) 2014 Canonical, Ltd
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Dustin Kirkland <kirkland@ubuntu.com>
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Seed Random
-----------
**Summary:** provide random seed data

Since all cloud instances started from the same image will produce very similar
data when they are first booted, as they are all starting with the same seed
for the kernel's entropy keyring. To avoid this, random seed data can be
provided to the instance either as a string or by specifying a command to run
to generate the data.

Configuration for this module is under the ``random_seed`` config key. The
``file`` key specifies the path to write the data to, defaulting to
``/dev/urandom``. Data can be passed in directly with ``data``, and may
optionally be specified in encoded form, with the encoding specified in
``encoding``.

.. note::
    when using a multiline value for ``data`` or specifying binary data, be
    sure to follow yaml syntax and use the ``|`` and ``!binary`` yaml format
    specifiers when appropriate

Instead of specifying a data string, a command can be run to generate/collect
the data to be written. The command should be specified as a list of args in
the ``command`` key. If a command is specified that cannot be run, no error
will be reported unless ``command_required`` is set to true.

For example, to use ``pollinate`` to gather data from a
remote entropy server and write it to ``/dev/urandom``, the following could be
used::

    random_seed:
        file: /dev/urandom
        command: ["pollinate", "--server=http://local.polinate.server"]
        command_required: true

**Internal name:** ``cc_seed_random``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    random_seed:
        file: <file>
        data: <random string>
        encoding: <raw/base64/b64/gzip/gz>
        command: [<cmd name>, <arg1>, <arg2>...]
        command_required: <true/false>
"""

import base64
import os

from six import BytesIO

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util

frequency = PER_INSTANCE
LOG = logging.getLogger(__name__)


def _decode(data, encoding=None):
    if not data:
        return b''
    if not encoding or encoding.lower() in ['raw']:
        return util.encode_text(data)
    elif encoding.lower() in ['base64', 'b64']:
        return base64.b64decode(data)
    elif encoding.lower() in ['gzip', 'gz']:
        return util.decomp_gzip(data, quiet=False, decode=None)
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
            raise ValueError(
                "command '{cmd}' not found but required=true".format(cmd=cmd))
        else:
            LOG.debug("command '%s' not found for seed_command", cmd)
            return
    util.subp(command, env=env, capture=False)


def handle(name, cfg, cloud, log, _args):
    mycfg = cfg.get('random_seed', {})
    seed_path = mycfg.get('file', '/dev/urandom')
    seed_data = mycfg.get('data', b'')

    seed_buf = BytesIO()
    if seed_data:
        seed_buf.write(_decode(seed_data, encoding=mycfg.get('encoding')))

    # 'random_seed' is set up by Azure datasource, and comes already in
    # openstack meta_data.json
    metadata = cloud.datasource.metadata
    if metadata and 'random_seed' in metadata:
        seed_buf.write(util.encode_text(metadata['random_seed']))

    seed_data = seed_buf.getvalue()
    if len(seed_data):
        log.debug("%s: adding %s bytes of random seed entropy to %s", name,
                  len(seed_data), seed_path)
        util.append_file(seed_path, seed_data)

    command = mycfg.get('command', None)
    req = mycfg.get('command_required', False)
    try:
        env = os.environ.copy()
        env['RANDOM_SEED_FILE'] = seed_path
        handle_random_seed_command(command=command, required=req, env=env)
    except ValueError as e:
        log.warn("handling random command [%s] failed: %s", command, e)
        raise e

# vi: ts=4 expandtab
