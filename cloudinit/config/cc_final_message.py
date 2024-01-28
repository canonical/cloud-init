# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Final Message: Output final message when cloud-init has finished"""

import logging
from textwrap import dedent

from cloudinit import templater, util, version
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

MODULE_DESCRIPTION = """\
This module configures the final message that cloud-init writes. The message is
specified as a jinja template with the following variables set:

    - ``version``: cloud-init version
    - ``timestamp``: time at cloud-init finish
    - ``datasource``: cloud-init data source
    - ``uptime``: system uptime

This message is written to the cloud-init log (usually /var/log/cloud-init.log)
as well as stderr (which usually redirects to /var/log/cloud-init-output.log).

Upon exit, this module writes the system uptime, timestamp, and cloud-init
version to ``/var/lib/cloud/instance/boot-finished`` independent of any
user data specified for this module.
"""
frequency = PER_ALWAYS
meta: MetaSchema = {
    "id": "cc_final_message",
    "name": "Final Message",
    "title": "Output final message when cloud-init has finished",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "examples": [
        dedent(
            """\
            final_message: |
              cloud-init has finished
              version: $version
              timestamp: $timestamp
              datasource: $datasource
              uptime: $uptime
            """
        )
    ],
    "activate_by_schema_keys": [],
}

LOG = logging.getLogger(__name__)
__doc__ = get_meta_doc(meta)

# Jinja formated default message
FINAL_MESSAGE_DEF = (
    "## template: jinja\n"
    "Cloud-init v. {{version}} finished at {{timestamp}}."
    " Datasource {{datasource}}.  Up {{uptime}} seconds"
)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:

    msg_in = ""
    if len(args) != 0:
        msg_in = str(args[0])
    else:
        msg_in = util.get_cfg_option_str(cfg, "final_message", "")

    msg_in = msg_in.strip()
    if not msg_in:
        msg_in = FINAL_MESSAGE_DEF

    uptime = util.uptime()
    ts = util.time_rfc2822()
    cver = version.version_string()
    try:
        subs = {
            "uptime": uptime,
            "timestamp": ts,
            "version": cver,
            "datasource": str(cloud.datasource),
        }
        subs.update(dict([(k.upper(), v) for k, v in subs.items()]))
        util.multi_log(
            "%s\n" % (templater.render_string(msg_in, subs)),
            console=False,
            stderr=True,
            log=LOG,
        )
    except templater.JinjaSyntaxParsingException as e:
        util.logexc(
            LOG, "Failed to render templated final message: %s", str(e)
        )
    except Exception:
        util.logexc(LOG, "Failed to render final message template")

    boot_fin_fn = cloud.paths.boot_finished
    try:
        contents = "%s - %s - v. %s\n" % (uptime, ts, cver)
        util.write_file(boot_fin_fn, contents, ensure_dir_exists=False)
    except Exception:
        util.logexc(LOG, "Failed to write boot finished file %s", boot_fin_fn)

    if cloud.datasource.is_disconnected:
        LOG.warning("Used fallback datasource")
