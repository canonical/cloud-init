# Copyright (C) 2009-2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Chad Smith <chad.smith@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Bootcmd: run arbitrary commands early in the boot process."""

import os
from textwrap import dedent

from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit.settings import PER_ALWAYS
from cloudinit import temp_utils
from cloudinit import util

frequency = PER_ALWAYS

# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.

distros = ['all']

schema = {
    'id': 'cc_bootcmd',
    'name': 'Bootcmd',
    'title': 'Run arbitrary commands early in the boot process',
    'description': dedent("""\
        This module runs arbitrary commands very early in the boot process,
        only slightly after a boothook would run. This is very similar to a
        boothook, but more user friendly. The environment variable
        ``INSTANCE_ID`` will be set to the current instance id for all run
        commands. Commands can be specified either as lists or strings. For
        invocation details, see ``runcmd``.

        .. note::
            bootcmd should only be used for things that could not be done later
            in the boot process.

        .. note::

          when writing files, do not use /tmp dir as it races with
          systemd-tmpfiles-clean LP: #1707222. Use /run/somedir instead.
    """),
    'distros': distros,
    'examples': [dedent("""\
        bootcmd:
            - echo 192.168.1.130 us.archive.ubuntu.com > /etc/hosts
            - [ cloud-init-per, once, mymkfs, mkfs, /dev/vdb ]
    """)],
    'frequency': PER_ALWAYS,
    'type': 'object',
    'properties': {
        'bootcmd': {
            'type': 'array',
            'items': {
                'oneOf': [
                    {'type': 'array', 'items': {'type': 'string'}},
                    {'type': 'string'}]
            },
            'additionalItems': False,  # Reject items of non-string non-list
            'additionalProperties': False,
            'minItems': 1,
            'required': [],
        }
    }
}

__doc__ = get_schema_doc(schema)  # Supplement python help()


def handle(name, cfg, cloud, log, _args):

    if "bootcmd" not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'bootcmd' key in configuration"), name)
        return

    validate_cloudconfig_schema(cfg, schema)
    with temp_utils.ExtendedTemporaryFile(suffix=".sh") as tmpf:
        try:
            content = util.shellify(cfg["bootcmd"])
            tmpf.write(util.encode_text(content))
            tmpf.flush()
        except Exception as e:
            util.logexc(log, "Failed to shellify bootcmd: %s", str(e))
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
