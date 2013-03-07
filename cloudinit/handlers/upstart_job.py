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

from cloudinit.settings import (PER_INSTANCE)

LOG = logging.getLogger(__name__)


class UpstartJobPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_INSTANCE)
        self.upstart_dir = paths.upstart_conf_d

    def list_types(self):
        return [
            handlers.type_from_starts_with("#upstart-job"),
        ]

    def handle_part(self, _data, ctype, filename,  # pylint: disable=W0221
                    payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            return

        # See: https://bugs.launchpad.net/bugs/819507
        if frequency != PER_INSTANCE:
            return

        if not self.upstart_dir:
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

        # FIXME LATER (LP: #1124384)
        # a bug in upstart means that invoking reload-configuration
        # at this stage in boot causes havoc.  So, until that is fixed
        # we will not do that.  However, I'd like to be able to easily
        # test to see if this bug is still present in an image with
        # a newer upstart.  So, a boot hook could easiliy write this file.
        if os.path.exists("/run/cloud-init-upstart-reload"):
            # if inotify support is not present in the root filesystem
            # (overlayroot) then we need to tell upstart to re-read /etc

            util.subp(["initctl", "reload-configuration"], capture=False)
