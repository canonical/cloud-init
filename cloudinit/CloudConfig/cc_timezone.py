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

from cloudinit.CloudConfig import per_instance
from cloudinit import util
import os.path
import shutil

frequency = per_instance
tz_base = "/usr/share/zoneinfo"


def handle(_name, cfg, _cloud, log, args):
    if len(args) != 0:
        timezone = args[0]
    else:
        timezone = util.get_cfg_option_str(cfg, "timezone", False)

    if not timezone:
        return

    tz_file = "%s/%s" % (tz_base, timezone)

    if not os.path.isfile(tz_file):
        log.debug("Invalid timezone %s" % tz_file)
        raise Exception("Invalid timezone %s" % tz_file)

    try:
        fp = open("/etc/timezone", "wb")
        fp.write("%s\n" % timezone)
        fp.close()
    except:
        log.debug("failed to write to /etc/timezone")
        raise
    if os.path.exists("/etc/sysconfig/clock"):
        try:
            with open("/etc/sysconfig/clock", "w") as fp:
                fp.write('ZONE="%s"\n' % timezone)
        except:
            log.debug("failed to write to /etc/sysconfig/clock")
            raise

    try:
        shutil.copy(tz_file, "/etc/localtime")
    except:
        log.debug("failed to copy %s to /etc/localtime" % tz_file)
        raise

    log.debug("set timezone to %s" % timezone)
    return
