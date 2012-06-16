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

from cloudinit import log as logging
from cloudinit import user_data as ud
from cloudinit import util

from cloudinit.settings import (PER_INSTANCE)

LOG = logging.getLogger(__name__)


class UpstartJobPartHandler(ud.PartHandler):
    def __init__(self, upstart_dir):
        ud.PartHandler.__init__(self, PER_INSTANCE)
        self.upstart_dir = upstart_dir

    def list_types(self):
        return [
            ud.type_from_starts_with("#upstart-job"),
        ]

    def _handle_part(self, _data, ctype, filename, payload, frequency):
        if ctype in ud.CONTENT_SIGNALS:
            return

        filename = util.clean_filename(filename)
        (_name, ext) = os.path.splitext(filename)
        if not ext:
            ext = ''
        ext = ext.lower()
        if ext != ".conf":
            filename = filename + ".conf"

        payload = util.dos2unix(payload)
        path = os.path.join(self.upstart_dir, filename)
        util.write_file(path, payload, 0644)
