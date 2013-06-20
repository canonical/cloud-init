# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2011 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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

from cloudinit.settings import PER_ALWAYS
from cloudinit import util

frequency = PER_ALWAYS


def handle(name, cfg, cloud, log, _args):

    if "bootcmd" not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'bootcmd' key in configuration"), name)
        return

    with util.ExtendedTemporaryFile(suffix=".sh") as tmpf:
        try:
            content = util.shellify(cfg["bootcmd"])
            tmpf.write(content)
            tmpf.flush()
        except:
            util.logexc(log, "Failed to shellify bootcmd")
            raise

        try:
            env = os.environ.copy()
            iid = cloud.get_instance_id()
            if iid:
                env['INSTANCE_ID'] = str(iid)
            cmd = ['/bin/sh', tmpf.name]
            util.subp(cmd, env=env, capture=False)
        except:
            util.logexc(log, "Failed to run bootcmd module %s", name)
            raise
