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

from cloudinit.CloudConfig import per_instance
import cloudinit.util as util
import subprocess

frequency = per_instance


def handle(_name, cfg, _cloud, log, _args):
    cmd = ['/usr/lib/cloud-init/write-ssh-key-fingerprints']
    fp_blacklist = util.get_cfg_option_list_or_str(cfg,
        "ssh_fp_console_blacklist", [])
    key_blacklist = util.get_cfg_option_list_or_str(cfg,
        "ssh_key_console_blacklist", ["ssh-dss"])
    try:
        confp = open('/dev/console', "wb")
        cmd.append(','.join(fp_blacklist))
        cmd.append(','.join(key_blacklist))
        subprocess.call(cmd, stdout=confp)
        confp.close()
    except:
        log.warn("writing keys to console value")
        raise
