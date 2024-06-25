# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Update Hostname: Update hostname and fqdn"""

import logging
import os

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_ALWAYS

meta: MetaSchema = {
    "id": "cc_update_hostname",
    "distros": ["all"],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        LOG.debug(
            "Configuration option 'preserve_hostname' is set,"
            " not updating the hostname in module %s",
            name,
        )
        return

    # Set prefer_fqdn_over_hostname value in distro
    hostname_fqdn = util.get_cfg_option_bool(
        cfg, "prefer_fqdn_over_hostname", None
    )
    if hostname_fqdn is not None:
        cloud.distro.set_option("prefer_fqdn_over_hostname", hostname_fqdn)

    # Set create_hostname_file in distro
    create_hostname_file = util.get_cfg_option_bool(
        cfg, "create_hostname_file", None
    )
    if create_hostname_file is not None:
        cloud.distro.set_option("create_hostname_file", create_hostname_file)

    (hostname, fqdn, is_default) = util.get_hostname_fqdn(cfg, cloud)
    if is_default and hostname == "localhost":
        # https://github.com/systemd/systemd/commit/d39079fcaa05e23540d2b1f0270fa31c22a7e9f1
        LOG.debug("Hostname is localhost. Let other services handle this.")
        return

    try:
        prev_fn = os.path.join(cloud.get_cpath("data"), "previous-hostname")
        LOG.debug("Updating hostname to %s (%s)", fqdn, hostname)
        cloud.distro.update_hostname(hostname, fqdn, prev_fn)
    except Exception:
        util.logexc(
            LOG, "Failed to update the hostname to %s (%s)", fqdn, hostname
        )
        raise
