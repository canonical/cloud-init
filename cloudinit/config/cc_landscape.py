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

from StringIO import StringIO

from configobj import ConfigObj

from cloudinit import type_utils
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

LSC_CLIENT_CFG_FILE = "/etc/landscape/client.conf"
LS_DEFAULT_FILE = "/etc/default/landscape-client"

distros = ['ubuntu']

# defaults taken from stock client.conf in landscape-client 11.07.1.1-0ubuntu2
LSC_BUILTIN_CFG = {
  'client': {
    'log_level': "info",
    'url': "https://landscape.canonical.com/message-system",
    'ping_url': "http://landscape.canonical.com/ping",
    'data_path': "/var/lib/landscape/client",
  }
}


def handle(_name, cfg, cloud, log, _args):
    """
    Basically turn a top level 'landscape' entry with a 'client' dict
    and render it to ConfigObj format under '[client]' section in
    /etc/landscape/client.conf
    """

    ls_cloudcfg = cfg.get("landscape", {})

    if not isinstance(ls_cloudcfg, (dict)):
        raise RuntimeError(("'landscape' key existed in config,"
                            " but not a dictionary type,"
                            " is a %s instead"),
                           type_utils.obj_name(ls_cloudcfg))
    if not ls_cloudcfg:
        return

    cloud.distro.install_packages(('landscape-client',))

    merge_data = [
        LSC_BUILTIN_CFG,
        LSC_CLIENT_CFG_FILE,
        ls_cloudcfg,
    ]
    merged = merge_together(merge_data)
    contents = StringIO()
    merged.write(contents)

    util.ensure_dir(os.path.dirname(LSC_CLIENT_CFG_FILE))
    util.write_file(LSC_CLIENT_CFG_FILE, contents.getvalue())
    log.debug("Wrote landscape config file to %s", LSC_CLIENT_CFG_FILE)

    util.write_file(LS_DEFAULT_FILE, "RUN=1\n")
    util.subp(["service", "landscape-client", "restart"])


def merge_together(objs):
    """
    merge together ConfigObj objects or things that ConfigObj() will take in
    later entries override earlier
    """
    cfg = ConfigObj({})
    for obj in objs:
        if not obj:
            continue
        if isinstance(obj, ConfigObj):
            cfg.merge(obj)
        else:
            cfg.merge(ConfigObj(obj))
    return cfg
