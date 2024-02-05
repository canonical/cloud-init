# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""install and configure landscape client"""

import logging
from itertools import chain
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
            # Minimum viable config requires account_name and computer_title
            landscape:
                client:
                    computer_title: kiosk 1
                    account_name: Joe's Biz
            """
        ),
        dedent(
            """\
           # To install landscape-client from a PPA, specify apt.sources
           apt:
               sources:
                 trunk-testing-ppa:
                   source: ppa:landscape/self-hosted-beta
           landscape:
               client:
                 account_name: myaccount
                 computer_title: himom
           """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["landscape"],
}

__doc__ = get_meta_doc(meta)
LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
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
    cloud.distro.install_packages(["landscape-client"])

    # Later order config values override earlier values
    merge_data = [
        LSC_BUILTIN_CFG,
        LSC_CLIENT_CFG_FILE,
        ls_cloudcfg,
    ]
    # Flatten dict k,v pairs to [--KEY1, VAL1, --KEY2, VAL2, ...]
    cmd_params = list(
        chain(
            *[
                [f"--{k.replace('_', '-')}", v]
                for k, v in sorted(
                    merge_together(merge_data)["client"].items()
                )
            ]
        )
    )
    try:
        subp.subp(["landscape-config", "--silent", "--is-registered"], rcs=[5])
        subp.subp(["landscape-config", "--silent"] + cmd_params)
    except subp.ProcessExecutionError as e:
        if e.exit_code == 0:
            LOG.warning("Client already registered to Landscape")
        else:
            msg = f"Failure registering client:\n{e}"
            util.logexc(LOG, msg)
            raise RuntimeError(msg) from e


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
