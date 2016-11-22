# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Locale
------
**Summary:** set system locale

Configure the system locale and apply it system wide. By default use the locale
specified by the datasource.

**Internal name:** ``cc_locale``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    locale: <locale str>
    locale_configfile: <path to locale config file>
"""

from cloudinit import util


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        locale = args[0]
    else:
        locale = util.get_cfg_option_str(cfg, "locale", cloud.get_locale())

    if util.is_false(locale):
        log.debug("Skipping module named %s, disabled by config: %s",
                  name, locale)
        return

    log.debug("Setting locale to %s", locale)
    locale_cfgfile = util.get_cfg_option_str(cfg, "locale_configfile")
    cloud.distro.apply_locale(locale, locale_cfgfile)

# vi: ts=4 expandtab
