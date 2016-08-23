# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

def handle(_name,cfg,cloud,log,_args):
    if not cfg.has_key("runcmd"):
        return
    outfile="%s/runcmd" % cloud.get_ipath('scripts')
    try:
        content = util.shellify(cfg["runcmd"])
        util.write_file(outfile,content,0700)
    except:
        log.warn("failed to open %s for runcmd" % outfile)
