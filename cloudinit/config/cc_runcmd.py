# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

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

# vi: ts=4 expandtab
