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

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)


class CloudConfigPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)
        self.cloud_buf = []
        self.cloud_fn = paths.get_ipath("cloud_config")

    def list_types(self):
        return [
            handlers.type_from_starts_with("#cloud-config"),
        ]

    def _write_cloud_config(self, buf):
        if not self.cloud_fn:
            return
        lines = [str(b) for b in buf]
        payload = "\n".join(lines)
        util.write_file(self.cloud_fn, payload, 0600)

    def _handle_part(self, _data, ctype, filename, payload, _frequency):
        if ctype == handlers.CONTENT_START:
            self.cloud_buf = []
            return
        if ctype == handlers.CONTENT_END:
            self._write_cloud_config(self.cloud_buf)
            self.cloud_buf = []
            return

        filename = util.clean_filename(filename)
        if not filename:
            filename = '??'
        self.cloud_buf.extend(["#%s" % (filename), str(payload)])
