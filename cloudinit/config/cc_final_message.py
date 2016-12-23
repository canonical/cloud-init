# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Final Message
-------------
**Summary:** output final message when cloud-init has finished

This module configures the final message that cloud-init writes. The message is
specified as a jinja template with the following variables set:

    - ``version``: cloud-init version
    - ``timestamp``: time at cloud-init finish
    - ``datasource``: cloud-init data source
    - ``uptime``: system uptime

**Internal name:** ``cc_final_message``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    final_message: <message>

"""

from cloudinit import templater
from cloudinit import util
from cloudinit import version

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS

# Jinja formated default message
FINAL_MESSAGE_DEF = (
    "## template: jinja\n"
    "Cloud-init v. {{version}} finished at {{timestamp}}."
    " Datasource {{datasource}}.  Up {{uptime}} seconds"
)


def handle(_name, cfg, cloud, log, args):

    msg_in = ''
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
            'uptime': uptime,
            'timestamp': ts,
            'version': cver,
            'datasource': str(cloud.datasource),
        }
        subs.update(dict([(k.upper(), v) for k, v in subs.items()]))
        util.multi_log("%s\n" % (templater.render_string(msg_in, subs)),
                       console=False, stderr=True, log=log)
    except Exception:
        util.logexc(log, "Failed to render final message template")

    boot_fin_fn = cloud.paths.boot_finished
    try:
        contents = "%s - %s - v. %s\n" % (uptime, ts, cver)
        util.write_file(boot_fin_fn, contents)
    except Exception:
        util.logexc(log, "Failed to write boot finished file %s", boot_fin_fn)

    if cloud.datasource.is_disconnected:
        log.warn("Used fallback datasource")

# vi: ts=4 expandtab
