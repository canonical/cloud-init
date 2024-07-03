# Copyright (C) 2011 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Apt Pipelining: configure apt pipelining."""

import logging

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

DEFAULT_FILE = "/etc/apt/apt.conf.d/90cloud-init-pipelining"
APT_PIPE_TPL = (
    "//Written by cloud-init per 'apt_pipelining'\n"
    'Acquire::http::Pipeline-Depth "%s";\n'
)
# Acquire::http::Pipeline-Depth can be a value
# from 0 to 5 indicating how many outstanding requests APT should send.
# A value of zero MUST be specified if the remote host does not properly linger
# on TCP connections - otherwise data corruption will occur.

meta: MetaSchema = {
    "id": "cc_apt_pipelining",
    "distros": ["ubuntu", "debian"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["apt_pipelining"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    apt_pipe_value = cfg.get("apt_pipelining", "os")
    apt_pipe_value_s = str(apt_pipe_value).lower().strip()

    if apt_pipe_value_s == "false":
        write_apt_snippet("0", LOG, DEFAULT_FILE)
    elif apt_pipe_value_s in ("none", "unchanged", "os"):
        return
    elif apt_pipe_value_s in [str(b) for b in range(6)]:
        write_apt_snippet(apt_pipe_value_s, LOG, DEFAULT_FILE)
    else:
        LOG.warning("Invalid option for apt_pipelining: %s", apt_pipe_value)


def write_apt_snippet(setting, log, f_name):
    """Writes f_name with apt pipeline depth 'setting'."""

    file_contents = APT_PIPE_TPL % (setting)
    util.write_file(f_name, file_contents)
    log.debug("Wrote %s with apt pipeline depth setting %s", f_name, setting)
