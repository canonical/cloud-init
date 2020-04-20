# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'devel' subcommand argument parsers to include in cloud-init cmd."""

import argparse
from cloudinit.config import schema

from . import net_convert
from . import render


def get_parser(parser=None):
    if not parser:
        parser = argparse.ArgumentParser(
            prog='cloudinit-devel',
            description='Run development cloud-init tools')
    subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand')
    subparsers.required = True

    subcmds = [
        ('schema', 'Validate cloud-config files for document schema',
         schema.get_parser, schema.handle_schema_args),
        (net_convert.NAME, net_convert.__doc__,
         net_convert.get_parser, net_convert.handle_args),
        (render.NAME, render.__doc__,
         render.get_parser, render.handle_args)
    ]
    for (subcmd, helpmsg, get_parser, handler) in subcmds:
        parser = subparsers.add_parser(subcmd, help=helpmsg)
        get_parser(parser)
        parser.set_defaults(action=(subcmd, handler))

    return parser
