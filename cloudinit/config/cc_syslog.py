# vi: ts=4 expandtab
#
#    Copyright (C) 2015 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from cloudinit import log as logging
from cloudinit import util
from cloudinit.settings import PER_INSTANCE

import re

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE

BUILTIN_CFG = {
    'remotes_file': '/etc/rsyslog.d/20-cloudinit-remotes.conf',
    'remotes': {},
    'service_name': 'rsyslog',
}

COMMENT_RE = re.compile(r'[ ]*[#]+[ ]*')
HOST_PORT_RE = re.compile(
    r'^(?P<proto>[@]{0,2})'
    '(([[](?P<bracket_addr>[^\]]*)[\]])|(?P<addr>[^:]*))'
    '([:](?P<port>[0-9]+))?$')


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
    print("host_port: %s" % addr)
    print("port: %s" % port)

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
            buf += " @"
        elif self.proto == "tcp":
            buf += " @@"

        if ":" in self.addr:
            buf += "[" + self.addr + "]"
        else:
            buf += self.addr

        if self.port:
            buf += ":%s" % self.port

        if self.name:
            buf += " # %s" % self.name
        return buf


def remotes_to_rsyslog_cfg(remotes, header=None):
    if not remotes:
        return None
    lines = []
    if header is not None:
        lines.append(header)
    for name, line in remotes.items():
        try:
            lines.append(parse_remotes_line(line, name=name))
        except ValueError as e:
            LOG.warn("failed loading remote %s: %s [%s]", name, line, e)
    return '\n'.join(str(lines)) + '\n'


def reload_syslog(systemd, service='rsyslog'):
    if systemd:
        cmd = ['systemctl', 'reload-or-try-restart', service]
    else:
        cmd = ['service', service, 'reload']
    try:
        util.subp(cmd, capture=True)
    except util.ProcessExecutionError as e:
        LOG.warn("Failed to reload syslog using '%s': %s", ' '.join(cmd), e)


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('syslog')
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    remotes_file = mycfg.get('remotes_file')
    if util.is_false(remotes_file):
        LOG.debug("syslog/remotes_file empty, doing nothing")
        return

    remotes = mycfg.get('remotes', {})
    if remotes and not isinstance(remotes, dict):
        LOG.warn("syslog/remotes: content is not a dictionary")
        return

    config_data = remotes_to_rsyslog_cfg(
        remotes, header="#cloud-init syslog module")

    util.write_file(remotes_file, config_data)

    reload_syslog(
        systemd=cloud.distro.uses_systemd(),
        service=mycfg.get('service_name'))
