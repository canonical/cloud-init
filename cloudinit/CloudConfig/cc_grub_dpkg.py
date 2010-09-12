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
import os

def handle(name,cfg,cloud,log,args):
    
    idevs=None
    idevs_empty=None

    if "grub-dpkg" in cfg:
        idevs=util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices",None)
        idevs_empty=util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices_empty",None)

    if os.path.exists("/dev/sda1") and not os.path.exists("/dev/sda"):
        if idevs == None: idevs=""
        if idevs_empty == None: idevs_empty="true"
    else:
        if idevs_empty == None: idevs_empty="false"
        if idevs == None:
            idevs = "/dev/sda"
            for dev in ( "/dev/sda", "/dev/vda", "/dev/sda1", "/dev/vda1"):
                if os.path.exists(dev):
                    idevs = dev
                    break
                
    # now idevs and idevs_empty are set to determined values
    # or, those set by user

    dconf_sel = "grub-pc grub-pc/install_devices string %s\n" % idevs + \
        "grub-pc grub-pc/install_devices_empty boolean %s\n" % idevs_empty
    log.debug("setting grub debconf-set-selections with '%s','%s'" %
        (idevs,idevs_empty))

    try:
        util.subp(('debconf-set-selections'), dconf_sel)
    except:
        log.error("Failed to run debconf-set-selections for grub-dpkg")
        log.debug(traceback.format_exc())
