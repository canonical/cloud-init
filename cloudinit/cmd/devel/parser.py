# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'devel' subcommand argument parsers to include in cloud-init cmd."""

import argparse

from cloudinit.config import schema

from . import hotplug_hook, make_mime, net_convert, render


def get_parser(parser=None):
    if not parser:
        parser = argparse.ArgumentParser(
            prog="cloudinit-devel",
            description="Run development cloud-init tools",
        )
    subparsers = parser.add_subparsers(title="Subcommands", dest="subcommand")
    subparsers.required = True

    subcmds = [
        (
            hotplug_hook.NAME,
            hotplug_hook.__doc__,
            hotplug_hook.get_parser,
            hotplug_hook.handle_args,
        ),
        (
            "schema",
            "Validate cloud-config files for document schema",
            schema.get_parser,
            schema.handle_schema_args,
        ),
        (
            net_convert.NAME,
            net_convert.__doc__,
            net_convert.get_parser,
            net_convert.handle_args,
        ),
        (render.NAME, render.__doc__, render.get_parser, render.handle_args),
        (
            make_mime.NAME,
            make_mime.__doc__,
            make_mime.get_parser,
            make_mime.handle_args,
        ),
    ]
    for (subcmd, helpmsg, get_parser, handler) in subcmds:
        parser = subparsers.add_parser(subcmd, help=helpmsg)
        get_parser(parser)
        parser.set_defaults(action=(subcmd, handler))

    return parser
