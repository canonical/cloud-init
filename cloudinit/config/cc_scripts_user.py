# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

SCRIPT_SUBDIR = 'scripts'


def handle(name, _cfg, cloud, log, _args):
    # This is written to by the user data handlers
    # Ie, any custom shell scripts that come down
    # go here...
    runparts_path = os.path.join(cloud.get_ipath_cur(), SCRIPT_SUBDIR)
    try:
        util.runparts(runparts_path)
    except:
        log.warn("Failed to run module %s (%s in %s)",
                 name, SCRIPT_SUBDIR, runparts_path)
        raise
