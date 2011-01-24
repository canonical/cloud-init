# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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
from cloudinit.CloudConfig import per_instance
import subprocess

frequency = per_instance

def handle(name,cfg,cloud,log,args):
    write_ssh_prog='/usr/lib/cloud-init/write-ssh-key-fingerprints'
    try:
        confp = open('/dev/console',"wb")
        subprocess.call(write_ssh_prog,stdout=confp)
        confp.close()
    except:
        log.warn("writing keys to console value")
        raise
