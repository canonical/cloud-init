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

import os

from cloudinit import templater
from cloudinit import util


def apply_locale(locale, cfgfile, cloud, log):
    # TODO this command might not work on RH...
    if os.path.exists('/usr/sbin/locale-gen'):
        util.subp(['locale-gen', locale], capture=False)
    if os.path.exists('/usr/sbin/update-locale'):
        util.subp(['update-locale', locale], capture=False)
    if not cfgfile:
        return
    template_fn = cloud.get_template_filename('default-locale')
    if not template_fn:
        log.warn("No template filename found to write to %s", cfgfile)
    else:
        templater.render_to_file(template_fn, cfgfile, {'locale': locale})


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        locale = args[0]
    else:
        locale = util.get_cfg_option_str(cfg, "locale", cloud.get_locale())

    locale_cfgfile = util.get_cfg_option_str(cfg, "locale_configfile",
                                             "/etc/default/locale")

    if not locale:
        log.debug(("Skipping module named %s, "
                   "no 'locale' configuration found"), name)
        return

    log.debug("Setting locale to %s", locale)

    apply_locale(locale, locale_cfgfile, cloud, log)
