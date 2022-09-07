# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Runcmd: run arbitrary commands at rc.local with output to the console"""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.


MODULE_DESCRIPTION = """\
Run arbitrary commands at a rc.local like time-frame with output to the
console. Each item can be either a list or a string. The item type affects
how it is executed:


* If the item is a string, it will be interpreted by ``sh``.
* If the item is a list, the items will be executed as if passed to execve(3)
  (with the first arg as the command).

Note that the ``runcmd`` module only writes the script to be run
later. The module that actually runs the script is ``scripts-user``
in the :ref:`topics/boot:Final` boot stage.

.. note::

    all commands must be proper yaml, so you have to quote any characters
    yaml would eat (':' can be problematic)

.. note::

    when writing files, do not use /tmp dir as it races with
    systemd-tmpfiles-clean LP: #1707222. Use /run/somedir instead.
"""

meta: MetaSchema = {
    "id": "cc_runcmd",
    "name": "Runcmd",
    "title": "Run arbitrary commands",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
        runcmd:
            - [ ls, -l, / ]
            - [ sh, -xc, "echo $(date) ': hello world!'" ]
            - [ sh, -c, echo "=========hello world'=========" ]
            - ls -l /root
            - [ wget, "http://example.org", -O, /tmp/index.html ]
    """
        )
    ],
    "activate_by_schema_keys": ["runcmd"],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if "runcmd" not in cfg:
        log.debug(
            "Skipping module named %s, no 'runcmd' key in configuration", name
        )
        return

    out_fn = os.path.join(cloud.get_ipath("scripts"), "runcmd")
    cmd = cfg["runcmd"]
    try:
        content = util.shellify(cmd)
        util.write_file(out_fn, content, 0o700)
    except Exception as e:
        raise type(e)("Failed to shellify {} into file {}".format(cmd, out_fn))


# vi: ts=4 expandtab
