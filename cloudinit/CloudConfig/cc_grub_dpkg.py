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

shcmd="""
unset idevs idevs_empty
if [ -n "${1}" ]; then
    idevs=${1}
    [ "$1" = "None" ] && idevs=""
fi
if [ -n "${2}" ]; then
    idevs_empty=${2}
    [ "$2" = "None" ] && idevs_empty=""
fi

f_idevs=""
f_idevs_empty=""
if [ -b /dev/sda1 -a ! -e /dev/sda ]; then
  f_idevs=""
  f_idevs_empty=true
else
  f_idevs=/dev/sda
  for dev in /dev/sda /dev/vda /dev/sda1 /dev/vda1; do
      [ -b "${dev}" ] && f_idevs=${dev} && break;
  done
  f_idevs_empty=false
fi

idevs=${idevs-${f_idevs}}
idevs_empty=${idevs_empty-${f_idevs_empty}}

printf "%s\t%s\t%s\t%s\n%s\t%s\t%s\t%s\n" \
  grub-pc grub-pc/install_devices string "${idevs}" \
  grub-pc grub-pc/install_devices_empty boolean "${idevs_empty}" |
  debconf-set-selections
"""

def handle(name,cfg,cloud,log,args):
    
    idevs=""
    idevs_empty=""

    if "grub-dpkg" in cfg:
        idevs=util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices","")
        idevs_empty=util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices_empty","")

    cmd = [ "/bin/sh", "-c", shcmd, 'grub-dpkg', idevs, idevs_empty ]

    log.debug("invoking grub-dpkg with '%s','%s'" % (idevs,idevs_empty))

    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd returned %s: %s" % ( e.returncode, cmd))
    except OSError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd failed to execute: %s" % ( cmd ))
