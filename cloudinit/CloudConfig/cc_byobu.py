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

import cloudinit.util as util
import subprocess
import traceback


def handle(_name, cfg, _cloud, log, args):
    if len(args) != 0:
        value = args[0]
    else:
        value = util.get_cfg_option_str(cfg, "byobu_by_default", "")

    if not value:
        return

    if value == "user" or value == "system":
        value = "enable-%s" % value

    valid = ("enable-user", "enable-system", "enable",
             "disable-user", "disable-system", "disable")
    if not value in valid:
        log.warn("Unknown value %s for byobu_by_default" % value)

    mod_user = value.endswith("-user")
    mod_sys = value.endswith("-system")
    if value.startswith("enable"):
        bl_inst = "install"
        dc_val = "byobu byobu/launch-by-default boolean true"
        mod_sys = True
    else:
        if value == "disable":
            mod_user = True
            mod_sys = True
        bl_inst = "uninstall"
        dc_val = "byobu byobu/launch-by-default boolean false"

    shcmd = ""
    if mod_user:
        user = util.get_cfg_option_str(cfg, "user", "ubuntu")
        shcmd += " sudo -Hu \"%s\" byobu-launcher-%s" % (user, bl_inst)
        shcmd += " || X=$(($X+1)); "
    if mod_sys:
        shcmd += "echo \"%s\" | debconf-set-selections" % dc_val
        shcmd += " && dpkg-reconfigure byobu --frontend=noninteractive"
        shcmd += " || X=$(($X+1)); "

    cmd = ["/bin/sh", "-c", "%s %s %s" % ("X=0;", shcmd, "exit $X")]

    log.debug("setting byobu to %s" % value)

    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd returned %s: %s" % (e.returncode, cmd))
    except OSError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd failed to execute: %s" % (cmd))
