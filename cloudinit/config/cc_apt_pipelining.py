# Copyright (C) 2011 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Apt Pipelining
--------------
**Summary:** configure apt pipelining

This module configures apt's ``Acquite::http::Pipeline-Depth`` option, whcih
controls how apt handles HTTP pipelining. It may be useful for pipelining to be
disabled, because some web servers, such as S3 do not pipeline properly (LP:
#948461). The ``apt_pipelining`` config key may be set to ``false`` to disable
pipelining altogether. This is the default behavior. If it is set to ``none``,
``unchanged``, or ``os``, no change will be made to apt configuration and the
default setting for the distro will be used. The pipeline depth can also be
manually specified by setting ``apt_pipelining`` to a number. However, this is
not recommended.

**Internal name:** ``cc_apt_pipelining``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::
    apt_pipelining: <false/none/unchanged/os/number>
"""

from cloudinit.settings import PER_INSTANCE
from cloudinit import util

frequency = PER_INSTANCE

distros = ['ubuntu', 'debian']

DEFAULT_FILE = "/etc/apt/apt.conf.d/90cloud-init-pipelining"

APT_PIPE_TPL = ("//Written by cloud-init per 'apt_pipelining'\n"
                'Acquire::http::Pipeline-Depth "%s";\n')

# Acquire::http::Pipeline-Depth can be a value
# from 0 to 5 indicating how many outstanding requests APT should send.
# A value of zero MUST be specified if the remote host does not properly linger
# on TCP connections - otherwise data corruption will occur.


def handle(_name, cfg, _cloud, log, _args):

    apt_pipe_value = util.get_cfg_option_str(cfg, "apt_pipelining", False)
    apt_pipe_value_s = str(apt_pipe_value).lower().strip()

    if apt_pipe_value_s == "false":
        write_apt_snippet("0", log, DEFAULT_FILE)
    elif apt_pipe_value_s in ("none", "unchanged", "os"):
        return
    elif apt_pipe_value_s in [str(b) for b in range(0, 6)]:
        write_apt_snippet(apt_pipe_value_s, log, DEFAULT_FILE)
    else:
        log.warn("Invalid option for apt_pipeling: %s", apt_pipe_value)


def write_apt_snippet(setting, log, f_name):
    """Writes f_name with apt pipeline depth 'setting'."""

    file_contents = APT_PIPE_TPL % (setting)
    util.write_file(f_name, file_contents)
    log.debug("Wrote %s with apt pipeline depth setting %s", f_name, setting)

# vi: ts=4 expandtab
