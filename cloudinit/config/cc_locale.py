# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Locale: set system locale"""

from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

distros = ["all"]

meta: MetaSchema = {
    "id": "cc_locale",
    "name": "Locale",
    "title": "Set system locale",
    "description": dedent(
        """\
        Configure the system locale and apply it system wide. By default use
        the locale specified by the datasource."""
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
            # Set the locale to ar_AE
            locale: ar_AE
            """
        ),
        dedent(
            """\
            # Set the locale to fr_CA in /etc/alternate_path/locale
            locale: fr_CA
            locale_configfile: /etc/alternate_path/locale
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if len(args) != 0:
        locale = args[0]
    else:
        locale = util.get_cfg_option_str(cfg, "locale", cloud.get_locale())

    if util.is_false(locale):
        log.debug(
            "Skipping module named %s, disabled by config: %s", name, locale
        )
        return

    log.debug("Setting locale to %s", locale)
    locale_cfgfile = util.get_cfg_option_str(cfg, "locale_configfile")
    cloud.distro.apply_locale(locale, locale_cfgfile)


# vi: ts=4 expandtab
