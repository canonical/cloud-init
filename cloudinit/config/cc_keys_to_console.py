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
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

# This is a tool that cloud init provides
HELPER_TOOL_TPL = "%s/cloud-init/write-ssh-key-fingerprints"

distros = ["all"]

meta: MetaSchema = {
    "id": "cc_keys_to_console",
    "name": "Keys to Console",
    "title": "Control which SSH host keys may be written to console",
    "description": (
        "For security reasons it may be desirable not to write SSH host keys"
        " and their fingerprints to the console. To avoid either being written"
        " to the console the ``emit_keys_to_console`` config key under the"
        " main ``ssh`` config key can be used. To avoid the fingerprint of"
        " types of SSH host keys being written to console the"
        " ``ssh_fp_console_blacklist`` config key can be used. By default,"
        " all types of keys will have their fingerprints written to console."
        " To avoid host keys of a key type being written to console the"
        "``ssh_key_console_blacklist`` config key can be used. By default"
        " all supported host keys are written to console."
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
            # Do not print any SSH keys to system console
            ssh:
              emit_keys_to_console: false
            """
        ),
        dedent(
            """\
            # Do not print certain ssh key types to console
            ssh_key_console_blacklist: [rsa]
            """
        ),
        dedent(
            """\
            # Do not print specific ssh key fingerprints to console
            ssh_fp_console_blacklist:
            - E25451E0221B5773DEBFF178ECDACB160995AA89
            - FE76292D55E8B28EE6DB2B34B2D8A784F8C0AAB0
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}
__doc__ = get_meta_doc(meta)

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
