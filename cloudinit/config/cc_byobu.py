# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Byobu: Enable/disable byobu system wide and for default user."""

import logging

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ug_util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_byobu",
    "distros": ["ubuntu", "debian"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if len(args) != 0:
        value = args[0]
    else:
        value = util.get_cfg_option_str(cfg, "byobu_by_default", "")

    if not value:
        LOG.debug("Skipping module named %s, no 'byobu' values found", name)
        return

    if value == "user" or value == "system":
        value = "enable-%s" % value

    valid = (
        "enable-user",
        "enable-system",
        "enable",
        "disable-user",
        "disable-system",
        "disable",
    )
    if value not in valid:
        LOG.warning("Unknown value %s for byobu_by_default", value)

    mod_user = value.endswith("-user")
    mod_sys = value.endswith("-system")
    if value.startswith("enable"):
        bl_inst = "install"
        dc_val = "byobu byobu/launch-by-default boolean true"
        mod_sys = True
    else:
        if value == "disable":
            mod_user = True
            mod_sys = True
        bl_inst = "uninstall"
        dc_val = "byobu byobu/launch-by-default boolean false"

    shcmd = ""
    if mod_user:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        if not user:
            LOG.warning(
                "No default byobu user provided, "
                "can not launch %s for the default user",
                bl_inst,
            )
        else:
            shcmd += ' sudo -Hu "%s" byobu-launcher-%s' % (user, bl_inst)
            shcmd += " || X=$(($X+1)); "
    if mod_sys:
        shcmd += 'echo "%s" | debconf-set-selections' % dc_val
        shcmd += " && dpkg-reconfigure byobu --frontend=noninteractive"
        shcmd += " || X=$(($X+1)); "

    if len(shcmd):
        cmd = ["/bin/sh", "-c", "%s %s %s" % ("X=0;", shcmd, "exit $X")]
        LOG.debug("Setting byobu to %s", value)
        subp.subp(cmd, capture=False)
