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
import subprocess
import traceback

def handle(name,cfg,cloud,log,args):
    if len(args) != 0:
        value = args[0]
    else:
        value = util.get_cfg_option_str(cfg,"byobu_by_default","")

    if not value: return

    if value == "user":
        user = util.get_cfg_option_str(cfg,"user","ubuntu")
        cmd = [ 'sudo', '-Hu', user, 'byobu-launcher-install' ]
    elif value == "system":
        shcmd="echo '%s' | debconf-set-selections && %s" % \
            ( "byobu byobu/launch-by-default boolean true", 
              "dpkg-reconfigure byobu --frontend=noninteractive" )
        cmd = [ "/bin/sh", "-c", shcmd ]
    else:
        log.warn("Unknown value %s for byobu_by_default" % value)
        return

    log.debug("enabling byobu for %s" % value)

    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd returned %s: %s" % ( e.returncode, cmd))
    except OSError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd failed to execute: %s" % ( cmd ))
