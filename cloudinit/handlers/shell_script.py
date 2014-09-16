# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import os

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)
SHELL_PREFIX = "#!"


class ShellScriptPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)
        self.script_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.script_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def list_types(self):
        return [
            handlers.type_from_starts_with(SHELL_PREFIX),
        ]

    def handle_part(self, data, ctype, filename, payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            # TODO(harlowja): maybe delete existing things here
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        path = os.path.join(self.script_dir, filename)
        util.write_file(path, payload, 0700)
