# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Ben Howard <ben.howard@canonical.com>
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

from cloudinit import distros
from cloudinit.distros import debian
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util
from cloudinit.settings import PER_INSTANCE
import hashlib
import pwd

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):

    distro_name = 'ubuntu'
    __default_user_name__ = 'ubuntu'

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)

    def get_default_user(self):
        return self.__default_user_name__

    def add_default_user(self):
        # Adds the ubuntu user using the rules:
        #  - Password is 'ubuntu', but is locked
        #  - nopasswd sudo access

        self.create_user(self.__default_user_name__,
                        plain_text_passwd=self.__default_user_name__,
                        home="/home/%s" % self.__default_user_name__,
                        shell="/bin/bash",
                        lockpasswd=True,
                        gecos="Ubuntu",
                        sudo="ALL=(ALL) NOPASSWD:ALL")

        LOG.info("Added default 'ubuntu' user with passwordless sudo")

    def create_user(self, name, **kargs):

        if not super(Distro, self).create_user(name, **kargs):
            return False

        if 'sshimportid' in kargs:
            cmd = ["sudo", "-Hu", name, "ssh-import-id"] + kargs['sshimportid']
            LOG.debug("Importing ssh ids for user %s, post user creation."
                        % name)

            try:
                util.subp(cmd, capture=True)
            except util.ProcessExecutionError as e:
                util.logexc(LOG, "Failed to import %s ssh ids", name)
                raise e

        return True
