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
        warn("failed to initfs, likely bad things to come: %s" % str(e))
        

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

    try:
        if util.get_cfg_option_bool(cloud.cfg,"preserve_hostname",False):
            log.debug("preserve_hostname is set. not managing hostname")
        else:
            hostname = cloud.get_hostname()
            cloud.sem_and_run("set_hostname", "once-per-instance",
                set_hostname, [ hostname, log ], False)
            cloud.sem_and_run("update_hostname", "always",
                update_hostname, [ hostname, log ], False)
    except Exception, e:
        util.logexc(log)
        warn("failed to set hostname\n")

    #print "user data is:" + cloud.get_user_data()

    # finish, send the cloud-config event
    cloud.initctl_emit()

    sys.exit(0)

# read hostname from a 'hostname' file
# allow for comments and stripping line endings.
# if file doesn't exist, or no contents, return default
def read_hostname(filename, default=None):
    try:
        fp = open(filename,"r")
        lines = fp.readlines()
        fp.close()
        for line in lines:
            hpos = line.find("#")
            if hpos != -1:
                line = line[0:hpos]
            line = line.rstrip()
            if line:
                return line
    except IOError, e:
        if e.errno == errno.ENOENT: pass
    return default
    
def set_hostname(hostname, log):
    try:
        subprocess.Popen(['hostname', hostname]).communicate()
        util.write_file("/etc/hostname","%s\n" % hostname, 0644)
        log.debug("populated /etc/hostname with %s on first boot", hostname)
    except:
        log.error("failed to set_hostname")

def update_hostname(hostname, log):
    prev_file="%s/%s" % (cloudinit.get_cpath('datadir'),"previous-hostname")
    etc_file = "/etc/hostname"

    hostname_prev = None
    hostname_in_etc = None

    try:
        hostname_prev = read_hostname(prev_file)
    except:
        log.warn("Failed to open %s" % prev_file)
    
    try:
        hostname_in_etc = read_hostname(etc_file)
    except:
        log.warn("Failed to open %s" % etc_file)

    update_files = []
    if not hostname_prev or hostname_prev != hostname:
        update_files.append(prev_file)

    if (not hostname_in_etc or 
        (hostname_in_etc == hostname_prev and hostname_in_etc != hostname)):
        update_files.append(etc_file)

    try:
        for fname in update_files:
            util.write_file(fname,"%s\n" % hostname, 0644)
            log.debug("wrote %s to %s" % (hostname,fname))
    except:
        log.warn("failed to write hostname to %s" % fname)

    if hostname_in_etc and hostname_prev and hostname_in_etc != hostname_prev:
        log.debug("%s differs from %s. assuming user maintained" %
                  (prev_file,etc_file))

    if etc_file in update_files:
        log.debug("setting hostname to %s" % hostname)
        subprocess.Popen(['hostname', hostname]).communicate()

if __name__ == '__main__':
    main()
