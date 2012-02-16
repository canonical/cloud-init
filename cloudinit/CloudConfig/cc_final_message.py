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

from cloudinit.CloudConfig import per_always
import sys
from cloudinit import util, boot_finished
import time

frequency = per_always

final_message = "cloud-init boot finished at $TIMESTAMP. Up $UPTIME seconds"


def handle(_name, cfg, _cloud, log, args):
    if len(args) != 0:
        msg_in = args[0]
    else:
        msg_in = util.get_cfg_option_str(cfg, "final_message", final_message)

    try:
        uptimef = open("/proc/uptime")
        uptime = uptimef.read().split(" ")[0]
        uptimef.close()
    except IOError as e:
        log.warn("unable to open /proc/uptime\n")
        uptime = "na"

    try:
        ts = time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime())
    except:
        ts = "na"

    try:
        subs = {'UPTIME': uptime, 'TIMESTAMP': ts}
        sys.stdout.write("%s\n" % util.render_string(msg_in, subs))
    except Exception as e:
        log.warn("failed to render string to stdout: %s" % e)

    fp = open(boot_finished, "wb")
    fp.write(uptime + "\n")
    fp.close()
