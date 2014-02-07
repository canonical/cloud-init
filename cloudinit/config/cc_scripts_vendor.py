# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Canonical Ltd.
#
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

import os

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

SCRIPT_SUBDIR = 'vendor'


def handle(name, cfg, cloud, log, _args):
    # This is written to by the vendor data handlers
    # any vendor data shell scripts get placed in runparts_path
    runparts_path = os.path.join(cloud.get_ipath_cur(), 'scripts',
                                 SCRIPT_SUBDIR)

    prefix = util.get_cfg_by_path(cfg, ('vendor_data', 'prefix'), [])

    try:
        util.runparts(runparts_path, exe_prefix=prefix)
    except:
        log.warn("Failed to run module %s (%s in %s)",
                 name, SCRIPT_SUBDIR, runparts_path)
        raise
