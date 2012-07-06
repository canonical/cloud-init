# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        timezone = args[0]
    else:
        timezone = util.get_cfg_option_str(cfg, "timezone", False)

    if not timezone:
        log.debug("Skipping module named %s, no 'timezone' specified", name)
        return

    # Let the distro handle settings its timezone
    cloud.distro.set_timezone(timezone)
