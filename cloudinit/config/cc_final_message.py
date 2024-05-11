# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Final Message: Output final message when cloud-init has finished"""

import logging

from cloudinit import templater, util, version
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS
meta: MetaSchema = {
    "id": "cc_final_message",
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)

# Jinja formatted default message
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

    if cloud.datasource.dsname == "None":
        if cloud.datasource.sys_cfg.get("datasource_list") != ["None"]:
            LOG.warning("Used fallback datasource")
