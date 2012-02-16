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

import cloudinit.util as util
import subprocess
import errno
from cloudinit.CloudConfig import per_always

frequency = per_always


def handle(_name, cfg, cloud, log, _args):
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug("preserve_hostname is set. not updating hostname")
        return

    (hostname, _fqdn) = util.get_hostname_fqdn(cfg, cloud)
    try:
        prev = "%s/%s" % (cloud.get_cpath('data'), "previous-hostname")
        update_hostname(hostname, prev, log)
    except Exception:
        log.warn("failed to set hostname\n")
        raise


# read hostname from a 'hostname' file
# allow for comments and stripping line endings.
# if file doesn't exist, or no contents, return default
def read_hostname(filename, default=None):
    try:
        fp = open(filename, "r")
        lines = fp.readlines()
        fp.close()
        for line in lines:
            hpos = line.find("#")
            if hpos != -1:
                line = line[0:hpos]
            line = line.rstrip()
            if line:
                return line
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
    return default


def update_hostname(hostname, prev_file, log):
    etc_file = "/etc/hostname"

    hostname_prev = None
    hostname_in_etc = None

    try:
        hostname_prev = read_hostname(prev_file)
    except Exception as e:
        log.warn("Failed to open %s: %s" % (prev_file, e))

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
            util.write_file(fname, "%s\n" % hostname, 0644)
            log.debug("wrote %s to %s" % (hostname, fname))
    except:
        log.warn("failed to write hostname to %s" % fname)

    if hostname_in_etc and hostname_prev and hostname_in_etc != hostname_prev:
        log.debug("%s differs from %s. assuming user maintained" %
                  (prev_file, etc_file))

    if etc_file in update_files:
        log.debug("setting hostname to %s" % hostname)
        subprocess.Popen(['hostname', hostname]).communicate()
