#!/usr/bin/python
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

import subprocess
import sys

import cloudinit
import cloudinit.util as util
import cloudinit.CloudConfig as CC
import time
import logging
import errno

def warn(str):
    sys.stderr.write(str)

def main():
    cmds = ( "start", "start-local" )
    cmd = ""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    if not cmd in cmds:
        sys.stderr.write("bad command %s. use one of %s\n" % (cmd, cmds))
        sys.exit(1)

    now = time.strftime("%a, %d %b %Y %H:%M:%S %z")
    try:
       uptimef=open("/proc/uptime")
       uptime=uptimef.read().split(" ")[0]
       uptimef.close()
    except IOError as e:
       warn("unable to open /proc/uptime\n")
       uptime = "na"

    msg = "cloud-init %s running: %s. up %s seconds" % (cmd, now, uptime)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

    source_type = "all"
    if cmd == "start-local":
        source_type = "local"

    try:
        cloudinit.initfs()
    except Exception, e:
        warn("failed to initfs, likely bad things to come: %s\n" % str(e))
        

    cloudinit.logging_set_from_cfg_file()
    log = logging.getLogger()
    log.info(msg)

    # cache is not instance specific, so it has to be purged
    # but we want 'start' to benefit from a cache if
    # a previous start-local populated one
    if cmd == "start-local":
        cloudinit.purge_cache()

    cloud = cloudinit.CloudInit(source_type=source_type)

    try:
        cloud.get_data_source()
    except cloudinit.DataSourceNotFoundException as e:
        sys.stderr.write("no instance data found in %s\n" % cmd)
        sys.exit(1)

    # set this as the current instance
    cloud.set_cur_instance()

    # store the metadata
    cloud.update_cache()

    msg = "found data source: %s" % cloud.datasource
    sys.stderr.write(msg + "\n")
    log.debug(msg)

    # parse the user data (ec2-run-userdata.py)
    try:
        cloud.sem_and_run("consume_userdata", "once-per-instance",
            cloud.consume_userdata,[],False)
    except:
        warn("consuming user data failed!\n")
        raise

    # finish, send the cloud-config event
    cloud.initctl_emit()

    cfg_path = cloudinit.get_ipath_cur("cloud_config")
    cc = CC.CloudConfig(cfg_path, cloud)
    modules_list = CC.read_cc_modules(cc.cfg,"cloud_init_modules")

    failures = []
    if len(modules_list):
        failures = CC.run_cc_modules(cc,module_list,log)
    else:
        msg = "no cloud_init_modules to run"
        sys.stderr.write(msg + "\n")
        log.debug(msg)
        sys.exit(0)

    sys.exit(len(failures))

if __name__ == '__main__':
    main()
