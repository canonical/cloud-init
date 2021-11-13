# Copyright (C) 2021 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Defer writing certain files"""

from textwrap import dedent

from cloudinit.config.schema import validate_cloudconfig_schema
from cloudinit import util
from cloudinit.config.cc_write_files import (
    schema as write_files_schema, write_files, DEFAULT_DEFER)


schema = util.mergemanydict([
    {
        'id': 'cc_write_files_deferred',
        'name': 'Write Deferred Files',
        'title': dedent("""\
            write certain files, whose creation as been deferred, during
            final stage
        """),
        'description': dedent("""\
            This module is based on `'Write Files' <write-files>`__, and
            will handle all files from the write_files list, that have been
            marked as deferred and thus are not being processed by the
            write-files module.

            *Please note that his module is not exposed to the user through
            its own dedicated top-level directive.*
        """)
    },
    write_files_schema
])

# Not exposed, because related modules should document this behaviour
__doc__ = None


def handle(name, cfg, _cloud, log, _args):
    validate_cloudconfig_schema(cfg, schema)
    file_list = cfg.get('write_files', [])
    filtered_files = [
        f for f in file_list if util.get_cfg_option_bool(f,
                                                         'defer',
                                                         DEFAULT_DEFER)
    ]
    if not filtered_files:
        log.debug(("Skipping module named %s,"
                   " no deferred file defined in configuration"), name)
        return
    write_files(name, filtered_files)


# vi: ts=4 expandtab
