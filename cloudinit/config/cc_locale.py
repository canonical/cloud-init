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
