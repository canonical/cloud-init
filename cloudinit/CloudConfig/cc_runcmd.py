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
import cloudinit
import cloudinit.util as util

def handle(name,cfg,cloud,log,args):
    if not cfg.has_key("runcmd"):
        return
    outfile="%s/runcmd" % cloudinit.user_scripts_dir

    content="#!/bin/sh\n"
    escaped="%s%s%s%s" % ( "'", '\\', "'", "'" )
    try:
        for args in cfg["runcmd"]:
            # if the item is a list, wrap all items in single tick
            # if its not, then just write it directly
            if isinstance(args,list):
                fixed = [ ]
                for f in args:
                    fixed.append("'%s'" % str(f).replace("'",escaped))
                content="%s%s\n" % ( content, ' '.join(fixed) )
            else:
                content="%s%s\n" % ( content, str(args) )

        util.write_file(outfile,content,0700)
    except:
        log.warn("failed to open %s for runcmd" % outfile)
