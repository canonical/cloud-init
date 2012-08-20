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

import pwd

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):

    distro_name = 'ubuntu'
    __default_user_name__ = 'ubuntu-test'

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)

    def get_default_username(self):
        return self.__default_user_name__

    def add_default_user(self):
        # Adds the ubuntu user using the rules:
        #  - Password is 'ubuntu', but is locked
        #  - nopasswd sudo access


        if self.__default_user_name__ in [x[0] for x in pwd.getpwall()]:
            LOG.warn("'%s' user already exists, not creating it." % \
                    self.__default_user_name__)
            return

        try:
            util.subp(['adduser',
                        '--shell', '/bin/bash',
                        '--home', '/home/%s' % self.__default_user_name__,
                        '--disabled-password',
                        '--gecos', 'Ubuntu',
                        self.__default_user_name__,
                        ])

            pass_string = '%(u)s:%(u)s' % {'u': self.__default_user_name__}
            x_pass_string = '%(u)s:REDACTED' % {'u': self.__default_user_name__}
            util.subp(['chpasswd'], pass_string, logstring=x_pass_string)
            util.subp(['passwd', '-l', self.__default_user_name__])

            ubuntu_sudoers="""
# Added by cloud-init
# %(user)s user is default user in cloud-images.
# It needs passwordless sudo functionality.
%(user)s ALL=(ALL) NOPASSWD:ALL
""" % { 'user': self.__default_user_name__ }

            util.write_file('/etc/sudoers.d/90-cloud-init-ubuntu',
                            ubuntu_sudoers,
                            mode=0440)

            LOG.info("Added default 'ubuntu' user with passwordless sudo")

        except Exception as e:
            util.logexc(LOG, "Failed to create %s user\n%s" %
                        (self.__default_user_name__, e))
