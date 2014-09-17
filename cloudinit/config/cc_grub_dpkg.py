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

import os

from cloudinit import util

distros = ['ubuntu', 'debian']


def handle(_name, cfg, _cloud, log, _args):
    idevs = None
    idevs_empty = None

    if "grub-dpkg" in cfg:
        idevs = util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices", None)
        idevs_empty = util.get_cfg_option_str(cfg["grub-dpkg"],
            "grub-pc/install_devices_empty", None)

    if ((os.path.exists("/dev/sda1") and not os.path.exists("/dev/sda")) or
            (os.path.exists("/dev/xvda1")
            and not os.path.exists("/dev/xvda"))):
        if idevs is None:
            idevs = ""
        if idevs_empty is None:
            idevs_empty = "true"
    else:
        if idevs_empty is None:
            idevs_empty = "false"
        if idevs is None:
            idevs = "/dev/sda"
            for dev in ("/dev/sda", "/dev/vda", "/dev/xvda",
                        "/dev/sda1", "/dev/vda1", "/dev/xvda1"):
                if os.path.exists(dev):
                    idevs = dev
                    break

    # now idevs and idevs_empty are set to determined values
    # or, those set by user

    dconf_sel = (("grub-pc grub-pc/install_devices string %s\n"
                 "grub-pc grub-pc/install_devices_empty boolean %s\n") %
                 (idevs, idevs_empty))

    log.debug("Setting grub debconf-set-selections with '%s','%s'" %
        (idevs, idevs_empty))

    try:
        util.subp(['debconf-set-selections'], dconf_sel)
    except:
        util.logexc(log, "Failed to run debconf-set-selections for grub-dpkg")
