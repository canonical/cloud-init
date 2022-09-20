# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Set Hostname: Set hostname and FQDN"""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.atomic_helper import write_json
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE
MODULE_DESCRIPTION = """\
This module handles setting the system hostname and fully qualified domain
name (FQDN). If ``preserve_hostname`` is set, then the hostname will not be
altered.

A hostname and FQDN can be provided by specifying a full domain name under the
``FQDN`` key. Alternatively, a hostname can be specified using the ``hostname``
key, and the FQDN of the cloud will be used. If a FQDN specified with the
``hostname`` key, it will be handled properly, although it is better to use
the ``fqdn`` config key. If both ``fqdn`` and ``hostname`` are set,
the ``prefer_fqdn_over_hostname`` will force the use of FQDN in all distros
when true, and when false it will force the short hostname. Otherwise, the
hostname to use is distro-dependent.

.. note::
    cloud-init performs no hostname input validation before sending the
    hostname to distro-specific tools, and most tools will not accept a
    trailing dot on the FQDN.

This module will run in the init-local stage before networking is configured
if the hostname is set by metadata or user data on the local system.

This will occur on datasources like nocloud and ovf where metadata and user
data are available locally. This ensures that the desired hostname is applied
before any DHCP requests are performed on these platforms where dynamic DNS is
based on initial hostname.
"""

meta: MetaSchema = {
    "id": "cc_set_hostname",
    "name": "Set Hostname",
    "title": "Set hostname and FQDN",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "examples": [
        "preserve_hostname: true",
        dedent(
            """\
            hostname: myhost
            fqdn: myhost.example.com
            prefer_fqdn_over_hostname: true
            """
        ),
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


class SetHostnameError(Exception):
    """Raised when the distro runs into an exception when setting hostname.

    This may happen if we attempt to set the hostname early in cloud-init's
    init-local timeframe as certain services may not be running yet.
    """


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug(
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

    (hostname, fqdn, is_default) = util.get_hostname_fqdn(cfg, cloud)
    # Check for previous successful invocation of set-hostname

    # set-hostname artifact file accounts for both hostname and fqdn
    # deltas. As such, it's format is different than cc_update_hostname's
    # previous-hostname file which only contains the base hostname.
    # TODO consolidate previous-hostname and set-hostname artifact files and
    # distro._read_hostname implementation so we only validate  one artifact.
    prev_fn = os.path.join(cloud.get_cpath("data"), "set-hostname")
    prev_hostname = {}
    if os.path.exists(prev_fn):
        prev_hostname = util.load_json(util.load_file(prev_fn))
    hostname_changed = hostname != prev_hostname.get(
        "hostname"
    ) or fqdn != prev_hostname.get("fqdn")
    if not hostname_changed:
        log.debug("No hostname changes. Skipping set-hostname")
        return
    if is_default and hostname == "localhost":
        # https://github.com/systemd/systemd/commit/d39079fcaa05e23540d2b1f0270fa31c22a7e9f1
        log.debug("Hostname is localhost. Let other services handle this.")
        return
    log.debug("Setting the hostname to %s (%s)", fqdn, hostname)
    try:
        cloud.distro.set_hostname(hostname, fqdn)
    except Exception as e:
        msg = "Failed to set the hostname to %s (%s)" % (fqdn, hostname)
        util.logexc(log, msg)
        raise SetHostnameError("%s: %s" % (msg, e)) from e
    write_json(prev_fn, {"hostname": hostname, "fqdn": fqdn})


# vi: ts=4 expandtab
