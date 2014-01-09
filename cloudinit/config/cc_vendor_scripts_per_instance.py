# vi: ts=4 expandtab
#
#    Copyright (C) 2011-2014 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Ben Howard <ben.howard@canonical.com>
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

SCRIPT_SUBDIR = 'per-instance'


def handle(name, cfg, cloud, log, _args):
    runparts_path = os.path.join(cloud.get_cpath(), 'scripts', 'vendor',
                                 SCRIPT_SUBDIR)
    vendor_prefix = util.get_nested_option_as_list(cfg, 'vendor_data',
                                                   'prefix')
    try:
        util.runparts(runparts_path, exe_prefix=vendor_prefix)
    except:
        log.warn("Failed to run module %s (%s in %s)",
                 name, SCRIPT_SUBDIR, runparts_path)
        raise
