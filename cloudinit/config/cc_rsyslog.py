# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
.. _cc_rsyslog:

Rsyslog
-------
**Summary:** configure system loggig via rsyslog

This module configures remote system logging using rsyslog.

The rsyslog config file to write to can be specified in ``config_filename``,
which defaults to ``20-cloud-config.conf``. The rsyslog config directory to
write config files to may be specified in ``config_dir``, which defaults to
``/etc/rsyslog.d``.

A list of configurations for rsyslog can be specified under the ``configs`` key
in the ``rsyslog`` config. Each entry in ``configs`` is either a string or a
dictionary. Each config entry contains a configuration string and a file to
write it to. For config entries that are a dictionary, ``filename`` sets the
target filename and ``content`` specifies the config string to write. For
config entries that are only a string, the string is used as the config string
to write. If the filename to write the config to is not specified, the value of
the ``config_filename`` key is used. A file with the selected filename will be
written inside the directory specified by ``config_dir``.

The command to use to reload the rsyslog service after the config has been
updated can be specified in ``service_reload_command``. If this is set to
``auto``, then an appropriate command for the distro will be used. This is the
default behavior. To manually set the command, use a list of command args (e.g.
``[systemctl, restart, rsyslog]``).

Configuration for remote servers can be specified in ``configs``, but for
convenience it can be specified as key value pairs in ``remotes``. Each key
is the name for an rsyslog remote entry. Each value holds the contents of the
remote config for rsyslog. The config consists of the following parts:

    - filter for log messages (defaults to ``*.*``)
    - optional leading ``@`` or ``@@``, indicating udp and tcp respectively
      (defaults to ``@``, for udp)
    - ipv4 or ipv6 hostname or address. ipv6 addresses must be in ``[::1]``
      format, (e.g. ``@[fd00::1]:514``)
    - optional port number (defaults to ``514``)

This module will provide sane defaults for any part of the remote entry that is
not specified, so in most cases remote hosts can be specified just using
``<name>: <address>``.

For backwards compatibility, this module still supports legacy names for the
config entries. Legacy to new mappings are as follows:

    - ``rsyslog`` -> ``rsyslog/configs``
    - ``rsyslog_filename`` -> ``rsyslog/config_filename``
    - ``rsyslog_dir`` -> ``rsyslog/config_dir``

.. note::
    The legacy config format does not support specifying
    ``service_reload_command``.

**Internal name:** ``cc_rsyslog``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    rsyslog:
        config_dir: config_dir
        config_filename: config_filename
        configs:
            - "*.* @@192.158.1.1"
            - content: "*.*   @@192.0.2.1:10514"
              filename: 01-example.conf
            - content: |
                *.*   @@syslogd.example.com
        remotes:
            maas: "192.168.1.1"
            juju: "10.0.4.1"
        service_reload_command: [your, syslog, restart, command]

**Legacy config keys**::

    rsyslog:
        - "*.* @@192.158.1.1"
    rsyslog_dir: /etc/rsyslog-config.d/
    rsyslog_filename: 99-local.conf
"""

# Old rsyslog documentation, kept for reference:
#
# rsyslog module allows configuration of syslog logging via rsyslog
# Configuration is done under the cloud-config top level 'rsyslog'.
#
# Under 'rsyslog' you can define:
#   - configs:  [default=[]]
#     this is a list.  entries in it are a string or a dictionary.
#     each entry has 2 parts:
#        * content
#        * filename
#     if the entry is a string, then it is assigned to 'content'.
#     for each entry, content is written to the provided filename.
#     if filename is not provided, its default is read from 'config_filename'
#
#     Content here can be any valid rsyslog configuration.  No format
#     specific format is enforced.
#
#     For simply logging to an existing remote syslog server, via udp:
#       configs: ["*.* @192.168.1.1"]
#
#   - remotes: [default={}]
#     This is a dictionary of name / value pairs.
#     In comparison to 'config's, it is more focused in that it only supports
#     remote syslog configuration.  It is not rsyslog specific, and could
#     convert to other syslog implementations.
#
#     Each entry in remotes is a 'name' and a 'value'.
#      * name: an string identifying the entry.  good practice would indicate
#        using a consistent and identifiable string for the producer.
#        For example, the MAAS service could use 'maas' as the key.
#      * value consists of the following parts:
#        * optional filter for log messages
#          default if not present: *.*
#        * optional leading '@' or '@@' (indicates udp or tcp respectively).
#          default if not present (udp): @
#          This is rsyslog format for that. if not present, is '@'.
#        * ipv4 or ipv6 or hostname
#          ipv6 addresses must be in [::1] format. (@[fd00::1]:514)
#        * optional port
#          port defaults to 514
#
#   - config_filename: [default=20-cloud-config.conf]
#     this is the file name to use if none is provided in a config entry.
#
#   - config_dir: [default=/etc/rsyslog.d]
#     this directory is used for filenames that are not absolute paths.
#
#   - service_reload_command: [default="auto"]
#     this command is executed if files have been written and thus the syslog
#     daemon needs to be told.
#
# Note, since cloud-init 0.5 a legacy version of rsyslog config has been
# present and is still supported. See below for the mappings between old
# value and new value:
#    old value           -> new value
#    'rsyslog'           -> rsyslog/configs
#    'rsyslog_filename'  -> rsyslog/config_filename
#    'rsyslog_dir'       -> rsyslog/config_dir
#
# the legacy config does not support 'service_reload_command'.
#
# Example config:
#   #cloud-config
#   rsyslog:
#     configs:
#       - "*.* @@192.158.1.1"
#       - content: "*.*   @@192.0.2.1:10514"
#         filename: 01-example.conf
#       - content: |
#         *.*   @@syslogd.example.com
#     remotes:
#       maas: "192.168.1.1"
#       juju: "10.0.4.1"
#     config_dir: config_dir
#     config_filename: config_filename
#     service_reload_command: [your, syslog, restart, command]
#
# Example Legacy config:
#   #cloud-config
#   rsyslog:
#     - "*.* @@192.158.1.1"
#   rsyslog_dir: /etc/rsyslog-config.d/
#   rsyslog_filename: 99-local.conf

import os
import re
import six

from cloudinit import log as logging
from cloudinit import util

DEF_FILENAME = "20-cloud-config.conf"
DEF_DIR = "/etc/rsyslog.d"
DEF_RELOAD = "auto"
DEF_REMOTES = {}

KEYNAME_CONFIGS = 'configs'
KEYNAME_FILENAME = 'config_filename'
KEYNAME_DIR = 'config_dir'
KEYNAME_RELOAD = 'service_reload_command'
KEYNAME_LEGACY_FILENAME = 'rsyslog_filename'
KEYNAME_LEGACY_DIR = 'rsyslog_dir'
KEYNAME_REMOTES = 'remotes'

LOG = logging.getLogger(__name__)

COMMENT_RE = re.compile(r'[ ]*[#]+[ ]*')
HOST_PORT_RE = re.compile(
    r'^(?P<proto>[@]{0,2})'
    r'(([[](?P<bracket_addr>[^\]]*)[\]])|(?P<addr>[^:]*))'
    r'([:](?P<port>[0-9]+))?$')


def reload_syslog(command=DEF_RELOAD, systemd=False):
    service = 'rsyslog'
    if command == DEF_RELOAD:
        if systemd:
            cmd = ['systemctl', 'reload-or-try-restart', service]
        else:
            cmd = ['service', service, 'restart']
    else:
        cmd = command
    util.subp(cmd, capture=True)


def load_config(cfg):
    # return an updated config with entries of the correct type
    # support converting the old top level format into new format
    mycfg = cfg.get('rsyslog', {})

    if isinstance(cfg.get('rsyslog'), list):
        mycfg = {KEYNAME_CONFIGS: cfg.get('rsyslog')}
        if KEYNAME_LEGACY_FILENAME in cfg:
            mycfg[KEYNAME_FILENAME] = cfg[KEYNAME_LEGACY_FILENAME]
        if KEYNAME_LEGACY_DIR in cfg:
            mycfg[KEYNAME_DIR] = cfg[KEYNAME_LEGACY_DIR]

    fillup = (
        (KEYNAME_CONFIGS, [], list),
        (KEYNAME_DIR, DEF_DIR, six.string_types),
        (KEYNAME_FILENAME, DEF_FILENAME, six.string_types),
        (KEYNAME_RELOAD, DEF_RELOAD, six.string_types + (list,)),
        (KEYNAME_REMOTES, DEF_REMOTES, dict))

    for key, default, vtypes in fillup:
        if key not in mycfg or not isinstance(mycfg[key], vtypes):
            mycfg[key] = default

    return mycfg


def apply_rsyslog_changes(configs, def_fname, cfg_dir):
    # apply the changes in 'configs' to the paths in def_fname and cfg_dir
    # return a list of the files changed
    files = []
    for cur_pos, ent in enumerate(configs):
        if isinstance(ent, dict):
            if "content" not in ent:
                LOG.warning("No 'content' entry in config entry %s",
                            cur_pos + 1)
                continue
            content = ent['content']
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

    proto = toks.group('proto')
    addr = toks.group('addr') or toks.group('bracket_addr')
    port = toks.group('port')

    if addr.startswith("[") and not addr.endswith("]"):
        raise ValueError("host spec had invalid brackets: %s" % addr)

    if comment and not name:
        name = comment

    t = SyslogRemotesLine(name=name, match=match, proto=proto,
                          addr=addr, port=port)
    t.validate()
    return t


class SyslogRemotesLine(object):
    def __init__(self, name=None, match=None, proto=None, addr=None,
                 port=None):
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
            except ValueError:
                raise ValueError("port '%s' is not an integer" % self.port)

        if not self.addr:
            raise ValueError("address is required")

    def __repr__(self):
        return "[name=%s match=%s proto=%s address=%s port=%s]" % (
            self.name, self.match, self.proto, self.addr, self.port
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
    return '\n'.join(lines) + "\n"


def handle(name, cfg, cloud, log, _args):
    if 'rsyslog' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'rsyslog' key in configuration"), name)
        return

    mycfg = load_config(cfg)
    configs = mycfg[KEYNAME_CONFIGS]

    if mycfg[KEYNAME_REMOTES]:
        configs.append(
            remotes_to_rsyslog_cfg(
                mycfg[KEYNAME_REMOTES],
                header="# begin remotes",
                footer="# end remotes",
            ))

    if not mycfg['configs']:
        log.debug("Empty config rsyslog['configs'], nothing to do")
        return

    changes = apply_rsyslog_changes(
        configs=mycfg[KEYNAME_CONFIGS],
        def_fname=mycfg[KEYNAME_FILENAME],
        cfg_dir=mycfg[KEYNAME_DIR])

    if not changes:
        log.debug("restart of syslog not necessary, no changes made")
        return

    try:
        restarted = reload_syslog(
            command=mycfg[KEYNAME_RELOAD],
            systemd=cloud.distro.uses_systemd()),
    except util.ProcessExecutionError as e:
        restarted = False
        log.warn("Failed to reload syslog", e)

    if restarted:
        # This only needs to run if we *actually* restarted
        # syslog above.
        cloud.cycle_logging()
        # This should now use rsyslog if
        # the logging was setup to use it...
        log.debug("%s configured %s files", name, changes)

# vi: ts=4 expandtab syntax=python
