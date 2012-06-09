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

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)


class BootHookPartHandler(ud.PartHandler):
    def __init__(self, boothook_dir, instance_id):
        ud.PartHandler.__init__(self, PER_ALWAYS)
        self.boothook_dir = boothook_dir
        self.instance_id = instance_id

    def list_types(self):
        return [
            ud.type_from_starts_with("#cloud-boothook"),
        ]

    def _handle_part(self, _data, ctype, filename, payload, _frequency):
        if ctype in ud.CONTENT_SIGNALS:
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        prefix = "#cloud-boothook"
        start = 0
        if payload.startswith(prefix):
            start = len(prefix) + 1

        filepath = os.path.join(self.boothook_dir, filename)
        util.write_file(filepath, payload[start:], 0700)
        try:
            env = os.environ.copy()
            env['INSTANCE_ID'] = str(self.instance_id)
            util.subp([filepath], env=env)
        except util.ProcessExecutionError as e:
            LOG.error("Boothooks script %s returned %s", filepath, e.exit_code)
        except Exception as e:
            LOG.error("Boothooks unknown exception %s when running %s", e, filepath)
