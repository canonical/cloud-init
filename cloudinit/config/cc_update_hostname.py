# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Update Hostname: Update hostname and fqdn"""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_ALWAYS

MODULE_DESCRIPTION = """\
This module will update the system hostname and fqdn. If ``preserve_hostname``
is set ``true``, then the hostname will not be altered.

.. note::
    for instructions on specifying hostname and fqdn, see documentation for
    ``cc_set_hostname``
"""

distros = ["all"]

meta: MetaSchema = {
    "id": "cc_update_hostname",
    "name": "Update Hostname",
    "title": "Update hostname and fqdn",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
        # By default: when ``preserve_hostname`` is not specified cloud-init
        # updates ``/etc/hostname`` per-boot based on the cloud provided
        # ``local-hostname`` setting. If you manually change ``/etc/hostname``
        # after boot cloud-init will no longer modify it.
        #
        # This default cloud-init behavior is equivalent to this cloud-config:
        preserve_hostname: false
        """
        ),
        dedent(
            """\
        # Prevent cloud-init from updating the system hostname.
        preserve_hostname: true
        """
        ),
        dedent(
            """\
        # Prevent cloud-init from updating ``/etc/hostname``
        preserve_hostname: true
        """
        ),
        dedent(
            """\
        # Set hostname to "external.fqdn.me" instead of "myhost"
        fqdn: external.fqdn.me
        hostname: myhost
        prefer_fqdn_over_hostname: true
        """
        ),
        dedent(
            """\
        # Set hostname to "external" instead of "external.fqdn.me" when
        # cloud metadata provides the ``local-hostname``: "external.fqdn.me".
        prefer_fqdn_over_hostname: false
        """
        ),
    ],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug(
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

    (hostname, fqdn, is_default) = util.get_hostname_fqdn(cfg, cloud)
    if is_default and hostname == "localhost":
        # https://github.com/systemd/systemd/commit/d39079fcaa05e23540d2b1f0270fa31c22a7e9f1
        log.debug("Hostname is localhost. Let other services handle this.")
        return

    try:
        prev_fn = os.path.join(cloud.get_cpath("data"), "previous-hostname")
        log.debug("Updating hostname to %s (%s)", fqdn, hostname)
        cloud.distro.update_hostname(hostname, fqdn, prev_fn)
    except Exception:
        util.logexc(
            log, "Failed to update the hostname to %s (%s)", fqdn, hostname
        )
        raise


# vi: ts=4 expandtab
