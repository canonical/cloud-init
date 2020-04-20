# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)


class ShellScriptPartHandler(handlers.Handler):

    prefixes = ['#!']

    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)
        self.script_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.script_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def handle_part(self, data, ctype, filename, payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            # TODO(harlowja): maybe delete existing things here
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        path = os.path.join(self.script_dir, filename)
        util.write_file(path, payload, 0o700)

# vi: ts=4 expandtab
