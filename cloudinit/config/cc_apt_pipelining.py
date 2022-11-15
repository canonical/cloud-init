# Copyright (C) 2011 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Apt Pipelining: configure apt pipelining."""

from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE
distros = ["ubuntu", "debian"]
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
    "name": "Apt Pipelining",
    "title": "Configure apt pipelining",
    "description": dedent(
        """\
        This module configures apt's ``Acquite::http::Pipeline-Depth`` option,
        which controls how apt handles HTTP pipelining. It may be useful for
        pipelining to be disabled, because some web servers, such as S3 do not
        pipeline properly (LP: #948461).

        Value configuration options for this module are:

        * ``false`` (Default): disable pipelining altogether
        * ``none``, ``unchanged``, or ``os``: use distro default
        * ``<number>``: Manually specify pipeline depth. This is not recommended."""  # noqa: E501
    ),
    "distros": distros,
    "frequency": frequency,
    "examples": [
        "apt_pipelining: false",
        "apt_pipelining: none",
        "apt_pipelining: unchanged",
        "apt_pipelining: os",
        "apt_pipelining: 3",
    ],
    "activate_by_schema_keys": ["apt_pipelining"],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    apt_pipe_value = cfg.get("apt_pipelining", "os")
    apt_pipe_value_s = str(apt_pipe_value).lower().strip()

    if apt_pipe_value_s == "false":
        write_apt_snippet("0", log, DEFAULT_FILE)
    elif apt_pipe_value_s in ("none", "unchanged", "os"):
        return
    elif apt_pipe_value_s in [str(b) for b in range(0, 6)]:
        write_apt_snippet(apt_pipe_value_s, log, DEFAULT_FILE)
    else:
        log.warning("Invalid option for apt_pipelining: %s", apt_pipe_value)


def write_apt_snippet(setting, log, f_name):
    """Writes f_name with apt pipeline depth 'setting'."""

    file_contents = APT_PIPE_TPL % (setting)
    util.write_file(f_name, file_contents)
    log.debug("Wrote %s with apt pipeline depth setting %s", f_name, setting)


# vi: ts=4 expandtab
