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
import cloudinit.util as util
import subprocess
import traceback

def handle(name,cfg,cloud,log,args):
    if len(args) != 0:
        resize_root = False
        if str(value).lower() in [ 'true', '1', 'on', 'yes']:
            resize_root = True
    else:
        resize_root = util.get_cfg_option_bool(cfg,"resize_rootfs",True)

    if not resize_root: return

    log.debug("resizing root filesystem on first boot")

    cmd = ['blkid', '-c', '/dev/null', '-sTYPE', '-ovalue', '/dev/root']
    try:
        (fstype,err) = util.subp(cmd)
    except Exception as e:
        log.warn("Failed to get filesystem type via %s" % cmd)
        raise

    if fstype.startswith("ext"):
        resize_cmd = [ 'resize2fs', '/dev/root' ]
    elif fstype == "xfs":
        resize_cmd = [ 'xfs_growfs', '/dev/root' ]
    else:
        log.debug("not resizing unknown filesystem %s" % fstype)
        return

    try:
        (out,err) = util.subp(resize_cmd)
    except Exception as e:
        log.warn("Failed to resize filesystem (%s)" % resize_cmd)
        raise
        
