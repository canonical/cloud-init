# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Landscape
---------
**Summary:** install and configure landscape client

This module installs and configures ``landscape-client``. The landscape client
will only be installed if the key ``landscape`` is present in config. Landscape
client configuration is given under the ``client`` key under the main
``landscape`` config key. The config parameters are not interpreted by
cloud-init, but rather are converted into a ConfigObj formatted file and
written out to ``/etc/landscape/client.conf``.

The following default client config is provided, but can be overridden::

    landscape:
        client:
            log_level: "info"
            url: "https://landscape.canonical.com/message-system"
            ping_url: "http://landscape.canoncial.com/ping"
            data_path: "/var/lib/landscape/client"

.. note::
    see landscape documentation for client config keys

.. note::
    if ``tags`` is defined, its contents should be a string delimited with
    ``,`` rather than a list

**Internal name:** ``cc_landscape``

**Module frequency:** per instance

**Supported distros:** ubuntu

**Config keys**::

    landscape:
        client:
            url: "https://landscape.canonical.com/message-system"
            ping_url: "http://landscape.canonical.com/ping"
            data_path: "/var/lib/landscape/client"
            http_proxy: "http://my.proxy.com/foobar"
            https_proxy: "https://my.proxy.com/foobar"
            tags: "server,cloud"
            computer_title: "footitle"
            registration_key: "fookey"
            account_name: "fooaccount"
"""

import os

from six import StringIO

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

# vi: ts=4 expandtab
