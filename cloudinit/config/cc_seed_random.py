# Copyright (C) 2013 Yahoo! Inc.
# Copyright (C) 2014 Canonical, Ltd
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Dustin Kirkland <kirkland@ubuntu.com>
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Seed Random: Provide random seed data"""

import base64
import logging
from io import BytesIO

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_seed_random",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore


def _decode(data, encoding=None):
    if not data:
        return b""
    if not encoding or encoding.lower() in ["raw"]:
        return util.encode_text(data)
    elif encoding.lower() in ["base64", "b64"]:
        return base64.b64decode(data)
    elif encoding.lower() in ["gzip", "gz"]:
        return util.decomp_gzip(data, quiet=False, decode=None)
    else:
        raise IOError("Unknown random_seed encoding: %s" % (encoding))


def handle_random_seed_command(command, required, update_env):
    if not command and required:
        raise ValueError("no command found but required=true")
    elif not command:
        LOG.debug("no command provided")
        return

    cmd = command[0]
    if not subp.which(cmd):
        if required:
            raise ValueError(
                "command '{cmd}' not found but required=true".format(cmd=cmd)
            )
        else:
            LOG.debug("command '%s' not found for seed_command", cmd)
            return
    subp.subp(command, update_env=update_env, capture=False)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    mycfg = cfg.get("random_seed", {})
    seed_path = mycfg.get("file", "/dev/urandom")
    seed_data = mycfg.get("data", b"")

    seed_buf = BytesIO()
    if seed_data:
        seed_buf.write(_decode(seed_data, encoding=mycfg.get("encoding")))

    # 'random_seed' is set up by Azure datasource, and comes already in
    # openstack meta_data.json
    metadata = cloud.datasource.metadata
    if metadata and "random_seed" in metadata:
        seed_buf.write(util.encode_text(metadata["random_seed"]))

    seed_data = seed_buf.getvalue()
    if len(seed_data):
        LOG.debug(
            "%s: adding %s bytes of random seed entropy to %s",
            name,
            len(seed_data),
            seed_path,
        )
        util.append_file(seed_path, seed_data)

    command = mycfg.get("command", None)
    req = mycfg.get("command_required", False)
    try:
        handle_random_seed_command(
            command=command,
            required=req,
            update_env={"RANDOM_SEED_FILE": seed_path},
        )
    except ValueError as e:
        LOG.warning("handling random command [%s] failed: %s", command, e)
        raise e
