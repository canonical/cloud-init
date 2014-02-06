# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import os

from cloudinit.settings import PER_INSTANCE
from cloudinit import util

frequency = PER_INSTANCE

# This is a tool that cloud init provides
HELPER_TOOL = '/usr/lib/cloud-init/write-ssh-key-fingerprints'


def handle(name, cfg, _cloud, log, _args):
    if not os.path.exists(HELPER_TOOL):
        log.warn(("Unable to activate module %s,"
                  " helper tool not found at %s"), name, HELPER_TOOL)
        return

    fp_blacklist = util.get_cfg_option_list(cfg,
                                            "ssh_fp_console_blacklist", [])
    key_blacklist = util.get_cfg_option_list(cfg,
                                             "ssh_key_console_blacklist",
                                              ["ssh-dss"])

    try:
        cmd = [HELPER_TOOL]
        cmd.append(','.join(fp_blacklist))
        cmd.append(','.join(key_blacklist))
        (stdout, _stderr) = util.subp(cmd)
        util.multi_log("%s\n" % (stdout.strip()),
                       stderr=False, console=True)
    except:
        log.warn("Writing keys to the system console failed!")
        raise
