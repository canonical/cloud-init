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
import os.path
import subprocess
import traceback


def apply_locale(locale, cfgfile):
    if os.path.exists('/usr/sbin/locale-gen'):
        subprocess.Popen(['locale-gen', locale]).communicate()
    if os.path.exists('/usr/sbin/update-locale'):
        subprocess.Popen(['update-locale', locale]).communicate()

    util.render_to_file('default-locale', cfgfile, {'locale': locale})


def handle(_name, cfg, cloud, log, args):
    if len(args) != 0:
        locale = args[0]
    else:
        locale = util.get_cfg_option_str(cfg, "locale", cloud.get_locale())

    locale_cfgfile = util.get_cfg_option_str(cfg, "locale_configfile",
                                             "/etc/default/locale")

    if not locale:
        return

    log.debug("setting locale to %s" % locale)

    try:
        apply_locale(locale, locale_cfgfile)
    except Exception as e:
        log.debug(traceback.format_exc(e))
        raise Exception("failed to apply locale %s" % locale)
