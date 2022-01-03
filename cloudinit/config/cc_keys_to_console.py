# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Keys to Console
---------------
**Summary:** control which SSH host keys may be written to console

For security reasons it may be desirable not to write SSH host keys and their
fingerprints to the console. To avoid either being written to the console the
``emit_keys_to_console`` config key under the main ``ssh`` config key can be
used. To avoid the fingerprint of types of SSH host keys being written to
console the ``ssh_fp_console_blacklist`` config key can be used. By default
all types of keys will have their fingerprints written to console. To avoid
host keys of a key type being written to console the
``ssh_key_console_blacklist`` config key can be used. By default ``ssh-dss``
host keys are not written to console.

**Internal name:** ``cc_keys_to_console``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    ssh:
      emit_keys_to_console: false

    ssh_fp_console_blacklist: <list of key types>
    ssh_key_console_blacklist: <list of key types>
"""

import os

from cloudinit import subp, util
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

# This is a tool that cloud init provides
HELPER_TOOL_TPL = "%s/cloud-init/write-ssh-key-fingerprints"


def _get_helper_tool_path(distro):
    try:
        base_lib = distro.usr_lib_exec
    except AttributeError:
        base_lib = "/usr/lib"
    return HELPER_TOOL_TPL % base_lib


def handle(name, cfg, cloud, log, _args):
    if util.is_false(cfg.get("ssh", {}).get("emit_keys_to_console", True)):
        log.debug(
            "Skipping module named %s, logging of SSH host keys disabled", name
        )
        return

    helper_path = _get_helper_tool_path(cloud.distro)
    if not os.path.exists(helper_path):
        log.warning(
            "Unable to activate module %s, helper tool not found at %s",
            name,
            helper_path,
        )
        return

    fp_blacklist = util.get_cfg_option_list(
        cfg, "ssh_fp_console_blacklist", []
    )
    key_blacklist = util.get_cfg_option_list(
        cfg, "ssh_key_console_blacklist", ["ssh-dss"]
    )

    try:
        cmd = [helper_path, ",".join(fp_blacklist), ",".join(key_blacklist)]
        (stdout, _stderr) = subp.subp(cmd)
        util.multi_log("%s\n" % (stdout.strip()), stderr=False, console=True)
    except Exception:
        log.warning("Writing keys to the system console failed!")
        raise


# vi: ts=4 expandtab
