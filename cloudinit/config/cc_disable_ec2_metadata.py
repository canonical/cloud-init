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

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS

REJECT_CMD = ['route', 'add', '-host', '169.254.169.254', 'reject']


def handle(name, cfg, _cloud, log, _args):
    disabled = util.get_cfg_option_bool(cfg, "disable_ec2_metadata", False)
    if disabled:
        util.subp(REJECT_CMD, capture=False)
    else:
        log.debug(("Skipping module named %s,"
                   " disabling the ec2 route not enabled"), name)
