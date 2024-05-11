# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Keys to Console: Control which SSH host keys may be written to console"""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

# This is a tool that cloud init provides
HELPER_TOOL_TPL = "%s/cloud-init/write-ssh-key-fingerprints"

meta: MetaSchema = {
    "id": "cc_keys_to_console",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


def _get_helper_tool_path(distro):
    try:
        base_lib = distro.usr_lib_exec
    except AttributeError:
        base_lib = "/usr/lib"
    return HELPER_TOOL_TPL % base_lib


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if util.is_false(cfg.get("ssh", {}).get("emit_keys_to_console", True)):
        LOG.debug(
            "Skipping module named %s, logging of SSH host keys disabled", name
        )
        return

    helper_path = _get_helper_tool_path(cloud.distro)
    if not os.path.exists(helper_path):
        LOG.warning(
            "Unable to activate module %s, helper tool not found at %s",
            name,
            helper_path,
        )
        return

    fp_blacklist = util.get_cfg_option_list(
        cfg, "ssh_fp_console_blacklist", []
    )
    key_blacklist = util.get_cfg_option_list(
        cfg, "ssh_key_console_blacklist", []
    )

    try:
        cmd = [helper_path, ",".join(fp_blacklist), ",".join(key_blacklist)]
        (stdout, _stderr) = subp.subp(cmd)
        util.multi_log("%s\n" % (stdout.strip()), stderr=False, console=True)
    except Exception:
        LOG.warning("Writing keys to the system console failed!")
        raise
