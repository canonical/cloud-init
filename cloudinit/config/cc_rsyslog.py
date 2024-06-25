# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2023 FreeBSD Foundation
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Mina Galić <FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Rsyslog: Configure system logging via rsyslog"""

import contextlib
import copy
import logging
import os
import re
from textwrap import dedent

from cloudinit import log, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_rsyslog",
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
        dedent(
            """\
            # default (no) configuration with package installation on FreeBSD
            rsyslog:
                config_dir: /usr/local/etc/rsyslog.d
                check_exe: "rsyslogd"
                packages: ["rsyslogd"]
                install_rsyslog: True
            """
        ),
    ],
    "activate_by_schema_keys": ["rsyslog"],
}  # type: ignore

RSYSLOG_CONFIG = {
    "config_dir": "/etc/rsyslog.d",
    "config_filename": "20-cloud-config.conf",
    "service_reload_command": "auto",
    "remotes": {},
    "configs": {},
    "check_exe": "rsyslogd",
    "packages": ["rsyslog"],
    "install_rsyslog": False,
}

DISTRO_OVERRIDES = {
    "freebsd": {
        "config_dir": "/usr/local/etc/rsyslog.d",
        "packages": ["rsyslog"],
    },
    "openbsd": {
        "config_dir": "/usr/local/etc/rsyslog.d",
        "packages": ["sysutils/rsyslog"],
    },
    "netbsd": {
        "config_dir": "/usr/pkg/etc/rsyslog.d",
        "packages": ["sysutils/rsyslog"],
    },
}

LOG = logging.getLogger(__name__)

COMMENT_RE = re.compile(r"[ ]*[#]+[ ]*")
HOST_PORT_RE = re.compile(
    r"^(?P<proto>[@]{0,2})"
    r"(([\[](?P<bracket_addr>[^\]]*)[\]])|(?P<addr>[^:]*))"
    r"([:](?P<port>[0-9]+))?$"
)


def distro_default_rsyslog_config(distro: Distro):
    """Construct a distro-specific rsyslog config dictionary by merging
       distro specific changes into base config.

    @param distro: String providing the distro class name.
    @returns: Dict of distro configurations for ntp clients.
    """
    dcfg = DISTRO_OVERRIDES
    cfg = copy.copy(RSYSLOG_CONFIG)
    if distro.osfamily in dcfg:
        cfg = util.mergemanydict([cfg, dcfg[distro.name]], reverse=True)
    return cfg


def install_rsyslog(install_func, packages=None, check_exe="rsyslog"):
    """Install rsyslog package if not already installed.

    @param install_func: function.  This parameter is invoked with the contents
    of the packages parameter.
    @param packages: list.  This parameter defaults to ['rsyslog'].
    @param check_exe: string.  The name of a binary that indicates the package
    the specified package is already installed.
    """
    if subp.which(check_exe):
        return
    if packages is None:
        packages = ["rsyslog"]

    install_func(packages)


def reload_syslog(distro, command="auto"):
    if command == "auto":
        service = distro.get_option("rsyslog_svcname", "rsyslog")
        return distro.manage_service("try-reload", service)
    return subp.subp(command, capture=True)


def load_config(cfg: dict, distro: Distro) -> dict:
    """Return an updated config.

    Support converting the old top level format into new format.
    Raise a `ValueError` if some top level entry has an incorrect type.
    """
    mycfg = cfg.get("rsyslog", {})
    distro_config = distro_default_rsyslog_config(distro)

    if isinstance(cfg.get("rsyslog"), list):
        util.deprecate(
            deprecated="The rsyslog key with value of type 'list'",
            deprecated_version="22.2",
        )
        mycfg = {"configs": cfg.get("rsyslog")}
        if "rsyslog_filename" in cfg:
            mycfg["config_filename"] = cfg["rsyslog_filename"]
        if "rsyslog_dir" in cfg:
            mycfg["config_dir"] = cfg["rsyslog_dir"]

    fillup: tuple = (
        ("configs", [], list),
        ("config_dir", distro_config["config_dir"], str),
        ("config_filename", distro_config["config_filename"], str),
        ("remotes", distro_config["remotes"], dict),
        (
            "service_reload_command",
            distro_config["service_reload_command"],
            (str, list),
        ),
        ("check_exe", distro_config["check_exe"], str),
        ("packages", distro_config["packages"], list),
        ("install_rsyslog", distro_config["install_rsyslog"], bool),
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


def disable_and_stop_bsd_base_syslog(cloud: Cloud) -> None:
    """
    This helper function bundles the necessary steps to disable BSD base syslog
    ``rc(8)`` reads its configuration on start, so after disabling syslogd, we
    need to tell rc to reload its config
    """
    try:
        cloud.distro.manage_service("enabled", "syslogd")
    except subp.ProcessExecutionError:
        return
    cloud.distro.manage_service("disable", "syslogd")
    cloud.distro.reload_init()

    with contextlib.suppress(subp.ProcessExecutionError):
        # for some inexplicable reason we're running after syslogd,
        # try to stop it, ignoring failures, only log the fact that
        # syslog is running, which it shouldn't be.
        cloud.distro.manage_service("onestop", "syslogd")
        LOG.error(
            "syslogd is running before cloud-init! "
            "Please report this as bug to the porters!"
        )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "rsyslog" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'rsyslog' key in configuration", name
        )
        return

    mycfg = load_config(cfg, cloud.distro)
    configs = mycfg["configs"]

    if mycfg["remotes"]:
        configs.append(
            remotes_to_rsyslog_cfg(
                mycfg["remotes"],
                header="# begin remotes",
                footer="# end remotes",
            )
        )

    service = cloud.distro.get_option("rsyslog_svcname", "rsyslog")

    if mycfg["install_rsyslog"] is True:
        install_rsyslog(
            cloud.distro.install_packages,
            packages=mycfg["packages"],
            check_exe=mycfg["check_exe"],
        )

    if util.is_BSD():
        cloud.distro.manage_service("enable", service)
        disable_and_stop_bsd_base_syslog(cloud)

    if not mycfg["configs"]:
        LOG.debug("Empty config rsyslog['configs'], nothing to do")
        return

    changes = apply_rsyslog_changes(
        configs=mycfg["configs"],
        def_fname=mycfg["config_filename"],
        cfg_dir=mycfg["config_dir"],
    )

    if not changes:
        LOG.debug("restart of syslog not necessary, no changes made")
        return

    try:
        restarted = reload_syslog(
            cloud.distro, command=mycfg["service_reload_command"]
        )
    except subp.ProcessExecutionError as e:
        restarted = False
        LOG.warning("Failed to reload syslog %s", str(e))

    if restarted:
        # This only needs to run if we *actually* restarted
        # syslog above.
        log.reset_logging()
        log.setup_logging(cloud.cfg)
        # This should now use rsyslog if
        # the logging was setup to use it...
        LOG.debug("%s configured %s files", name, changes)
