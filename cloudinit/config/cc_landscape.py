# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""install and configure landscape client"""

import os
from io import BytesIO
from logging import Logger
from textwrap import dedent

from configobj import ConfigObj

from cloudinit import subp, type_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

LSC_CLIENT_CFG_FILE = "/etc/landscape/client.conf"
LS_DEFAULT_FILE = "/etc/default/landscape-client"

# defaults taken from stock client.conf in landscape-client 11.07.1.1-0ubuntu2
LSC_BUILTIN_CFG = {
    "client": {
        "log_level": "info",
        "url": "https://landscape.canonical.com/message-system",
        "ping_url": "http://landscape.canonical.com/ping",
        "data_path": "/var/lib/landscape/client",
    }
}

MODULE_DESCRIPTION = """\
This module installs and configures ``landscape-client``. The landscape client
will only be installed if the key ``landscape`` is present in config. Landscape
client configuration is given under the ``client`` key under the main
``landscape`` config key. The config parameters are not interpreted by
cloud-init, but rather are converted into a ConfigObj formatted file and
written out to the `[client]` section in ``/etc/landscape/client.conf``.

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
"""
distros = ["ubuntu"]

meta: MetaSchema = {
    "id": "cc_landscape",
    "name": "Landscape",
    "title": "Install and configure landscape client",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
            # To discover additional supported client keys, run
            # man landscape-config.
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
        ),
        dedent(
            """\
            # Any keys below `client` are optional and the default values will
            # be used.
            landscape:
                client: {}
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["landscape"],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    """
    Basically turn a top level 'landscape' entry with a 'client' dict
    and render it to ConfigObj format under '[client]' section in
    /etc/landscape/client.conf
    """

    ls_cloudcfg = cfg.get("landscape", {})

    if not isinstance(ls_cloudcfg, (dict)):
        raise RuntimeError(
            "'landscape' key existed in config, but not a dictionary type,"
            " is a {_type} instead".format(
                _type=type_utils.obj_name(ls_cloudcfg)
            )
        )
    if not ls_cloudcfg:
        return

    cloud.distro.install_packages(("landscape-client",))

    # Later order config values override earlier values
    merge_data = [
        LSC_BUILTIN_CFG,
        LSC_CLIENT_CFG_FILE,
        ls_cloudcfg,
    ]
    merged = merge_together(merge_data)
    contents = BytesIO()
    merged.write(contents)

    util.ensure_dir(os.path.dirname(LSC_CLIENT_CFG_FILE))
    util.write_file(LSC_CLIENT_CFG_FILE, contents.getvalue())
    log.debug("Wrote landscape config file to %s", LSC_CLIENT_CFG_FILE)

    util.write_file(LS_DEFAULT_FILE, "RUN=1\n")
    subp.subp(["service", "landscape-client", "restart"])


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
