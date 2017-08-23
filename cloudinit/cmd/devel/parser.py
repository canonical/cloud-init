# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'devel' subcommand argument parsers to include in cloud-init cmd."""

import argparse
from cloudinit.config.schema import (
    get_parser as schema_parser, handle_schema_args)


def get_parser(parser=None):
    if not parser:
        parser = argparse.ArgumentParser(
            prog='cloudinit-devel',
            description='Run development cloud-init tools')
    subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand')
    subparsers.required = True

    parser_schema = subparsers.add_parser(
        'schema', help='Validate cloud-config files or document schema')
    # Construct schema subcommand parser
    schema_parser(parser_schema)
    parser_schema.set_defaults(action=('schema', handle_schema_args))

    return parser
