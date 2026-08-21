# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""install and configure landscape client"""

import configparser
import logging
from itertools import chain

from cloudinit import subp, type_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LSC_CLIENT_CFG_FILE = "/etc/landscape/client.conf"

# defaults taken from stock client.conf in landscape-client 11.07.1.1-0ubuntu2
LSC_BUILTIN_CFG = {
    "client": {
        "log_level": "info",
        "url": "https://landscape.canonical.com/message-system",
        "ping_url": "http://landscape.canonical.com/ping",
        "data_path": "/var/lib/landscape/client",
    }
}

meta: MetaSchema = {
    "id": "cc_landscape",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["landscape"],
}

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """
    Basically turn a top level 'landscape' entry with a 'client' dict
    and render it to INI format under '[client]' section in
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




def _parse_ini_file(filename):
    """Parse an INI file and return a nested dict {section: {key: value}}."""
    parser = configparser.RawConfigParser()
    parser.optionxform = str  # preserve key case
    try:
        parser.read(filename)
    except (configparser.Error, OSError):
        return {}
    result = {}
    for section in parser.sections():
        result[section] = dict(parser.items(section))
    return result


def merge_together(objs):
    """Merge together dicts or INI filenames; later entries override earlier."""
    result = {}
    for obj in objs:
        if not obj:
            continue
        if isinstance(obj, str):
            result = util.deep_merge(result, _parse_ini_file(obj))
        elif isinstance(obj, dict):
            result = util.deep_merge(result, obj)
    return result
