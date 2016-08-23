# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2011 Canonical Ltd.
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
import cloudinit.util as util
import subprocess
import tempfile
from cloudinit.CloudConfig import per_always
frequency = per_always

def handle(name,cfg,cloud,log,args):
    if not cfg.has_key("bootcmd"):
        return

    try:
        content = util.shellify(cfg["bootcmd"])
        tmpf = tempfile.TemporaryFile()
        tmpf.write(content)
        tmpf.seek(0)
    except:
        log.warn("failed to shellify bootcmd")
        raise
    
    try:
        env=os.environ.copy()
        env['INSTANCE_ID']=cloud.get_instance_id()
        subprocess.check_call(['/bin/sh'], env=env, stdin=tmpf)
        tmpf.close()
    except:
        log.warn("failed to run commands from bootcmd")
        raise
