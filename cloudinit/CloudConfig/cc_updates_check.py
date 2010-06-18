# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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
import cloudinit.util as util
import cloudinit
import os
import time

cronpre = "/etc/cron.d/cloudinit"

def handle(name,cfg,cloud,log,args):
    if not util.get_cfg_option_bool(cfg, 'updates-check', True):
        return
    build_info = "/etc/cloud/build.info"
    if not os.path.isfile(build_info):
        log.warn("no %s file" % build_info)

    avail="%s/%s" % ( cloudinit.datadir, "available.build" )
    cmd=( "uec-query-builds", "--system-suite", "--config", "%s" % build_info,
          "--output", "%s" % avail, "is-update-available" )
    try:
        util.subp(cmd)
    except:
        log.warn("failed to execute uec-query-build for updates check")

    # add a cron entry for this hour and this minute every day
    try:
        cron=open("%s-%s" % (cronpre, "updates") ,"w")
        cron.write("%s root %s\n" % \
            (time.strftime("%M %H * * *"),' '.join(cmd)))
        cron.close()
    except:
        log.warn("failed to enable cron update system check")
        raise

