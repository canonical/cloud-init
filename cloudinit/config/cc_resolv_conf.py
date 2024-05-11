# Copyright (C) 2013 Craig Tracey
# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Craig Tracey <craigtracey@gmail.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Resolv Conf: configure resolv.conf"""

import logging

from cloudinit import templater, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

RESOLVE_CONFIG_TEMPLATE_MAP = {
    "/etc/resolv.conf": "resolv.conf",
    "/etc/systemd/resolved.conf": "systemd.resolved.conf",
}

meta: MetaSchema = {
    "id": "cc_resolv_conf",
    "distros": [
        "alpine",
        "azurelinux",
        "fedora",
        "mariner",
        "opensuse",
        "opensuse-leap",
        "opensuse-microos",
        "opensuse-tumbleweed",
        "photon",
        "rhel",
        "sle_hpc",
        "sle-micro",
        "sles",
        "openeuler",
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["manage_resolv_conf"],
}  # type: ignore


def generate_resolv_conf(template_fn, params, target_fname):
    flags = []
    false_flags = []

    if "options" in params:
        for key, val in params["options"].items():
            if isinstance(val, bool):
                if val:
                    flags.append(key)
                else:
                    false_flags.append(key)

    for flag in flags + false_flags:
        del params["options"][flag]

    if not params.get("options"):
        params["options"] = {}

    params["flags"] = flags
    LOG.debug("Writing resolv.conf from template %s", template_fn)
    templater.render_to_file(template_fn, target_fname, params)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """
    Handler for resolv.conf

    @param name: The module name "resolv_conf" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param args: Any module arguments from cloud.cfg
    """
    if "manage_resolv_conf" not in cfg:
        LOG.debug(
            "Skipping module named %s,"
            " no 'manage_resolv_conf' key in configuration",
            name,
        )
        return

    if not util.get_cfg_option_bool(cfg, "manage_resolv_conf", False):
        LOG.debug(
            "Skipping module named %s,"
            " 'manage_resolv_conf' present but set to False",
            name,
        )
        return

    if "resolv_conf" not in cfg:
        LOG.warning("manage_resolv_conf True but no parameters provided!")
        return

    try:
        template_fn = cloud.get_template_filename(
            RESOLVE_CONFIG_TEMPLATE_MAP[cloud.distro.resolve_conf_fn]
        )
    except KeyError:
        LOG.warning("No template found, not rendering resolve configs")
        return

    generate_resolv_conf(
        template_fn=template_fn,
        params=cfg["resolv_conf"],
        target_fname=cloud.distro.resolve_conf_fn,
    )
    return
