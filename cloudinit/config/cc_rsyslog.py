# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Rsyslog: Configure system logging via rsyslog"""

import os
import re
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module configures remote system logging using rsyslog.

Configuration for remote servers can be specified in ``configs``, but for
convenience it can be specified as key value pairs in ``remotes``.
"""

meta: MetaSchema = {
    "id": "cc_rsyslog",
    "name": "Rsyslog",
    "title": "Configure system logging via rsyslog",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            rsyslog:
                remotes:
                    maas: 192.168.1.1
                    juju: 10.0.4.1
                service_reload_command: auto
            """
        ),
        dedent(
            """\
            rsyslog:
                config_dir: /opt/etc/rsyslog.d
                config_filename: 99-late-cloud-config.conf
                configs:
                    - "*.* @@192.158.1.1"
                    - content: "*.*   @@192.0.2.1:10514"
                      filename: 01-example.conf
                    - content: |
                        *.*   @@syslogd.example.com
                remotes:
                    maas: 192.168.1.1
                    juju: 10.0.4.1
                service_reload_command: [your, syslog, restart, command]
            """
        ),
    ],
    "activate_by_schema_keys": ["rsyslog"],
}

__doc__ = get_meta_doc(meta)

DEF_FILENAME = "20-cloud-config.conf"
DEF_DIR = "/etc/rsyslog.d"
DEF_RELOAD = "auto"
DEF_REMOTES: dict = {}

KEYNAME_CONFIGS = "configs"
KEYNAME_FILENAME = "config_filename"
KEYNAME_DIR = "config_dir"
KEYNAME_RELOAD = "service_reload_command"
KEYNAME_LEGACY_FILENAME = "rsyslog_filename"
KEYNAME_LEGACY_DIR = "rsyslog_dir"
KEYNAME_REMOTES = "remotes"

LOG = logging.getLogger(__name__)

COMMENT_RE = re.compile(r"[ ]*[#]+[ ]*")
HOST_PORT_RE = re.compile(
    r"^(?P<proto>[@]{0,2})"
    r"(([\[](?P<bracket_addr>[^\]]*)[\]])|(?P<addr>[^:]*))"
    r"([:](?P<port>[0-9]+))?$"
)


def reload_syslog(distro, command=DEF_RELOAD):
    if command == DEF_RELOAD:
        service = distro.get_option("rsyslog_svcname", "rsyslog")
        return distro.manage_service("try-reload", service)
    return subp.subp(command, capture=True)


def load_config(cfg: dict) -> dict:
    """Return an updated config.

    Support converting the old top level format into new format.
    Raise a `ValueError` if some top level entry has an incorrect type.
    """
    mycfg = cfg.get("rsyslog", {})

    if isinstance(cfg.get("rsyslog"), list):
        LOG.warning(
            "DEPRECATION: This rsyslog list format is deprecated and will be "
            "removed in a future version of cloud-init. Use documented keys."
        )
        mycfg = {KEYNAME_CONFIGS: cfg.get("rsyslog")}
        if KEYNAME_LEGACY_FILENAME in cfg:
            mycfg[KEYNAME_FILENAME] = cfg[KEYNAME_LEGACY_FILENAME]
        if KEYNAME_LEGACY_DIR in cfg:
            mycfg[KEYNAME_DIR] = cfg[KEYNAME_LEGACY_DIR]

    fillup: tuple = (
        (KEYNAME_CONFIGS, [], list),
        (KEYNAME_DIR, DEF_DIR, str),
        (KEYNAME_FILENAME, DEF_FILENAME, str),
        (KEYNAME_RELOAD, DEF_RELOAD, (str, list)),
        (KEYNAME_REMOTES, DEF_REMOTES, dict),
    )

    for key, default, vtypes in fillup:
        if key not in mycfg:
            mycfg[key] = default
        elif not isinstance(mycfg[key], vtypes):
            raise ValueError(
                f"Invalid type for key `{key}`. Expected type(s): {vtypes}. "
                f"Current type: {type(mycfg[key])}"
            )

    return mycfg


def apply_rsyslog_changes(configs, def_fname, cfg_dir):
    # apply the changes in 'configs' to the paths in def_fname and cfg_dir
    # return a list of the files changed
    files = []
    for cur_pos, ent in enumerate(configs):
        if isinstance(ent, dict):
            if "content" not in ent:
                LOG.warning(
                    "No 'content' entry in config entry %s", cur_pos + 1
                )
                continue
            content = ent["content"]
            filename = ent.get("filename", def_fname)
        else:
            content = ent
            filename = def_fname

        filename = filename.strip()
        if not filename:
            LOG.warning("Entry %s has an empty filename", cur_pos + 1)
            continue

        filename = os.path.join(cfg_dir, filename)

        # Truncate filename first time you see it
        omode = "ab"
        if filename not in files:
            omode = "wb"
            files.append(filename)

        try:
            endl = ""
            if not content.endswith("\n"):
                endl = "\n"
            util.write_file(filename, content + endl, omode=omode)
        except Exception:
            util.logexc(LOG, "Failed to write to %s", filename)

    return files


def parse_remotes_line(line, name=None):
    try:
        data, comment = COMMENT_RE.split(line)
        comment = comment.strip()
    except ValueError:
        data, comment = (line, None)

    toks = data.strip().split()
    match = None
    if len(toks) == 1:
        host_port = data
    elif len(toks) == 2:
        match, host_port = toks
    else:
        raise ValueError("line had multiple spaces: %s" % data)

    toks = HOST_PORT_RE.match(host_port)

    if not toks:
        raise ValueError("Invalid host specification '%s'" % host_port)

    proto = toks.group("proto")
    addr = toks.group("addr") or toks.group("bracket_addr")
    port = toks.group("port")

    if addr.startswith("[") and not addr.endswith("]"):
        raise ValueError("host spec had invalid brackets: %s" % addr)

    if comment and not name:
        name = comment

    t = SyslogRemotesLine(
        name=name, match=match, proto=proto, addr=addr, port=port
    )
    t.validate()
    return t


class SyslogRemotesLine:
    def __init__(
        self, name=None, match=None, proto=None, addr=None, port=None
    ):
        if not match:
            match = "*.*"
        self.name = name
        self.match = match
        if not proto:
            proto = "udp"
        if proto == "@":
            proto = "udp"
        elif proto == "@@":
            proto = "tcp"
        self.proto = proto

        self.addr = addr
        if port:
            self.port = int(port)
        else:
            self.port = None

    def validate(self):
        if self.port:
            try:
                int(self.port)
            except ValueError as e:
                raise ValueError(
                    "port '%s' is not an integer" % self.port
                ) from e

        if not self.addr:
            raise ValueError("address is required")

    def __repr__(self):
        return "[name=%s match=%s proto=%s address=%s port=%s]" % (
            self.name,
            self.match,
            self.proto,
            self.addr,
            self.port,
        )

    def __str__(self):
        buf = self.match + " "
        if self.proto == "udp":
            buf += "@"
        elif self.proto == "tcp":
            buf += "@@"

        if ":" in self.addr:
            buf += "[" + self.addr + "]"
        else:
            buf += self.addr

        if self.port:
            buf += ":%s" % self.port

        if self.name:
            buf += " # %s" % self.name
        return buf


def remotes_to_rsyslog_cfg(remotes, header=None, footer=None):
    if not remotes:
        return None
    lines = []
    if header is not None:
        lines.append(header)
    for name, line in remotes.items():
        if not line:
            continue
        try:
            lines.append(str(parse_remotes_line(line, name=name)))
        except ValueError as e:
            LOG.warning("failed loading remote %s: %s [%s]", name, line, e)
    if footer is not None:
        lines.append(footer)
    return "\n".join(lines) + "\n"


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if "rsyslog" not in cfg:
        log.debug(
            "Skipping module named %s, no 'rsyslog' key in configuration", name
        )
        return

    mycfg = load_config(cfg)
    configs = mycfg[KEYNAME_CONFIGS]

    if mycfg[KEYNAME_REMOTES]:
        configs.append(
            remotes_to_rsyslog_cfg(
                mycfg[KEYNAME_REMOTES],
                header="# begin remotes",
                footer="# end remotes",
            )
        )

    if not mycfg["configs"]:
        log.debug("Empty config rsyslog['configs'], nothing to do")
        return

    changes = apply_rsyslog_changes(
        configs=mycfg[KEYNAME_CONFIGS],
        def_fname=mycfg[KEYNAME_FILENAME],
        cfg_dir=mycfg[KEYNAME_DIR],
    )

    if not changes:
        log.debug("restart of syslog not necessary, no changes made")
        return

    try:
        restarted = reload_syslog(cloud.distro, command=mycfg[KEYNAME_RELOAD])
    except subp.ProcessExecutionError as e:
        restarted = False
        log.warning("Failed to reload syslog", e)

    if restarted:
        # This only needs to run if we *actually* restarted
        # syslog above.
        cloud.cycle_logging()
        # This should now use rsyslog if
        # the logging was setup to use it...
        log.debug("%s configured %s files", name, changes)


# vi: ts=4 expandtab syntax=python
