# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Set Hostname: Set hostname and FQDN"""

import logging
import os

from cloudinit import util
from cloudinit.atomic_helper import write_json
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_set_hostname",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


class SetHostnameError(Exception):
    """Raised when the distro runs into an exception when setting hostname.

    This may happen if we attempt to set the hostname early in cloud-init's
    init-local timeframe as certain services may not be running yet.
    """


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        LOG.debug(
            "Configuration option 'preserve_hostname' is set,"
            " not setting the hostname in module %s",
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
    # Check for previous successful invocation of set_hostname

    # set-hostname artifact file accounts for both hostname and fqdn
    # deltas. As such, it's format is different than cc_update_hostname's
    # previous-hostname file which only contains the base hostname.
    # TODO consolidate previous-hostname and set-hostname artifact files and
    # distro._read_hostname implementation so we only validate  one artifact.
    prev_fn = os.path.join(cloud.get_cpath("data"), "set-hostname")
    prev_hostname = {}
    if os.path.exists(prev_fn) and os.stat(prev_fn).st_size > 0:
        prev_hostname = util.load_json(util.load_text_file(prev_fn))
    hostname_changed = hostname != prev_hostname.get(
        "hostname"
    ) or fqdn != prev_hostname.get("fqdn")
    if not hostname_changed:
        LOG.debug("No hostname changes. Skipping set_hostname")
        return
    if is_default and hostname == "localhost":
        # https://github.com/systemd/systemd/commit/d39079fcaa05e23540d2b1f0270fa31c22a7e9f1
        LOG.debug("Hostname is localhost. Let other services handle this.")
        return
    LOG.debug("Setting the hostname to %s (%s)", fqdn, hostname)
    try:
        cloud.distro.set_hostname(hostname, fqdn)
    except Exception as e:
        msg = "Failed to set the hostname to %s (%s)" % (fqdn, hostname)
        util.logexc(LOG, msg)
        raise SetHostnameError("%s: %s" % (msg, e)) from e
    write_json(prev_fn, {"hostname": hostname, "fqdn": fqdn})
