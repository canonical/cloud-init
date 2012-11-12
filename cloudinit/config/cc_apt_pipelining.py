# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#
#    Author: Ben Howard <ben.howard@canonical.com>
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
    elif apt_pipe_value_s in [str(b) for b in xrange(0, 6)]:
        write_apt_snippet(apt_pipe_value_s, log, DEFAULT_FILE)
    else:
        log.warn("Invalid option for apt_pipeling: %s", apt_pipe_value)


def write_apt_snippet(setting, log, f_name):
    """Writes f_name with apt pipeline depth 'setting'."""

    file_contents = APT_PIPE_TPL % (setting)
    util.write_file(f_name, file_contents)
    log.debug("Wrote %s with apt pipeline depth setting %s", f_name, setting)
