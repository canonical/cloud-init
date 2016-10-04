# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

"""
Runcmd
------
**Summary:** run commands

Run arbitrary commands at a rc.local like level with output to the console.
Each item can be either a list or a string. If the item is a list, it will be
properly executed as if passed to ``execve()`` (with the first arg as the
command). If the item is a string, it will be written to a file and interpreted
using ``sh``.

.. note::
    all commands must be proper yaml, so you have to quote any characters yaml
    would eat (':' can be problematic)

**Internal name:** ``cc_runcmd``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    runcmd:
        - [ ls, -l, / ]
        - [ sh, -xc, "echo $(date) ': hello world!'" ]
        - [ sh, -c, echo "=========hello world'=========" ]
        - ls -l /root
        - [ wget, "http://example.org", -O, /tmp/index.html ]
"""


import os

from cloudinit import util


def handle(name, cfg, cloud, log, _args):
    if "runcmd" not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'runcmd' key in configuration"), name)
        return

    out_fn = os.path.join(cloud.get_ipath('scripts'), "runcmd")
    cmd = cfg["runcmd"]
    try:
        content = util.shellify(cmd)
        util.write_file(out_fn, content, 0o700)
    except Exception:
        util.logexc(log, "Failed to shellify %s into file %s", cmd, out_fn)
