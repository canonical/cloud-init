# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Grub Dpkg
---------
**Summary:** configure grub debconf installation device

Configure which device is used as the target for grub installation. This module
should work correctly by default without any user configuration. It can be
enabled/disabled using the ``enabled`` config key in the ``grub_dpkg`` config
dict. The global config key ``grub-dpkg`` is an alias for ``grub_dpkg``. If no
installation device is specified this module will look for the first existing
device in:

    - ``/dev/sda``
    - ``/dev/vda``
    - ``/dev/xvda``
    - ``/dev/sda1``
    - ``/dev/vda1``
    - ``/dev/xvda1``

**Internal name:** ``cc_grub_dpkg``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::

    grub_dpkg:
        enabled: <true/false>
        grub-pc/install_devices: <devices>
        grub-pc/install_devices_empty: <devices>
    grub-dpkg: (alias for grub_dpkg)
"""

import os

from cloudinit import util

distros = ['ubuntu', 'debian']


def handle(name, cfg, _cloud, log, _args):

    mycfg = cfg.get("grub_dpkg", cfg.get("grub-dpkg", {}))
    if not mycfg:
        mycfg = {}

    enabled = mycfg.get('enabled', True)
    if util.is_false(enabled):
        log.debug("%s disabled by config grub_dpkg/enabled=%s", name, enabled)
        return

    idevs = util.get_cfg_option_str(mycfg, "grub-pc/install_devices", None)
    idevs_empty = util.get_cfg_option_str(
        mycfg, "grub-pc/install_devices_empty", None)

    if ((os.path.exists("/dev/sda1") and not os.path.exists("/dev/sda")) or
       (os.path.exists("/dev/xvda1") and not os.path.exists("/dev/xvda"))):
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
    except Exception:
        util.logexc(log, "Failed to run debconf-set-selections for grub-dpkg")

# vi: ts=4 expandtab
