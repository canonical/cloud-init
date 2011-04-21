# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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
import subprocess

def handle(name,cfg,cloud,log,args):
    if util.get_cfg_option_bool(cfg,"preserve_hostname",False):
        log.debug("preserve_hostname is set. not setting hostname")
        return(True)

    try:
        hostname_prefix = util.get_cfg_option_str(cfg, "hostname_prefix", None)
        hostname_attr = util.get_cfg_option_str(cfg, "hostname_attribute", "hostname")
        hostname_function = getattr(cloud, 'get_' + hostname_attr, None)
        if hostname_fucntion is None: hostname_fucntion = cloud.get_hostname
        hostname = util.get_cfg_option_str(cfg,"hostname", hostname_function)
        if hostname_prefix: hostname = hostname_prefix + "-" + hostname
        set_hostname(hostname, log)
    except Exception as e:
        util.logexc(log)
        log.warn("failed to set hostname\n")

    return(True)

def set_hostname(hostname, log):
    subprocess.Popen(['hostname', hostname]).communicate()
    util.write_file("/etc/hostname","%s\n" % hostname, 0644)
    log.debug("populated /etc/hostname with %s on first boot", hostname)
