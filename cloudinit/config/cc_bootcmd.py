# Copyright (C) 2009-2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Bootcmd
-------
**Summary:** run commands early in boot process

This module runs arbitrary commands very early in the boot process,
only slightly after a boothook would run. This is very similar to a
boothook, but more user friendly. The environment variable ``INSTANCE_ID``
will be set to the current instance id for all run commands. Commands can be
specified either as lists or strings. For invocation details, see ``runcmd``.

.. note::
    bootcmd should only be used for things that could not be done later in the
    boot process.

**Internal name:** ``cc_bootcmd``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    bootcmd:
        - echo 192.168.1.130 us.archive.ubuntu.com > /etc/hosts
        - [ cloud-init-per, once, mymkfs, mkfs, /dev/vdb ]
"""

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
            tmpf.write(util.encode_text(content))
            tmpf.flush()
        except Exception:
            util.logexc(log, "Failed to shellify bootcmd")
            raise

        try:
            env = os.environ.copy()
            iid = cloud.get_instance_id()
            if iid:
                env['INSTANCE_ID'] = str(iid)
            cmd = ['/bin/sh', tmpf.name]
            util.subp(cmd, env=env, capture=False)
        except Exception:
            util.logexc(log, "Failed to run bootcmd module %s", name)
            raise

# vi: ts=4 expandtab
