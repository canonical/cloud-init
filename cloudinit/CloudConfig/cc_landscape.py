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
import os.path
from cloudinit.CloudConfig import per_instance
from configobj import ConfigObj

frequency = per_instance

lsc_client_cfg_file = "/etc/landscape/client.conf"

# defaults taken from stock client.conf in landscape-client 11.07.1.1-0ubuntu2
lsc_builtincfg = {
  'client': {
    'log_level': "info",
    'url': "https://landscape.canonical.com/message-system",
    'ping_url': "http://landscape.canonical.com/ping",
    'data_path': "/var/lib/landscape/client",
  }
}


def handle(_name, cfg, _cloud, log, _args):
    """
    Basically turn a top level 'landscape' entry with a 'client' dict
    and render it to ConfigObj format under '[client]' section in
    /etc/landscape/client.conf
    """

    ls_cloudcfg = cfg.get("landscape", {})

    if not isinstance(ls_cloudcfg, dict):
        raise(Exception("'landscape' existed in config, but not a dict"))

    merged = mergeTogether([lsc_builtincfg, lsc_client_cfg_file, ls_cloudcfg])

    if not os.path.isdir(os.path.dirname(lsc_client_cfg_file)):
        os.makedirs(os.path.dirname(lsc_client_cfg_file))

    with open(lsc_client_cfg_file, "w") as fp:
        merged.write(fp)

    log.debug("updated %s" % lsc_client_cfg_file)


def mergeTogether(objs):
    """
    merge together ConfigObj objects or things that ConfigObj() will take in
    later entries override earlier
    """
    cfg = ConfigObj({})
    for obj in objs:
        if isinstance(obj, ConfigObj):
            cfg.merge(obj)
        else:
            cfg.merge(ConfigObj(obj))
    return cfg
