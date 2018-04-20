# Copyright (C) 2018 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Ubuntu advantage: manage ubuntu-advantage offerings from Canonical."""

import sys
from textwrap import dedent

from cloudinit import log as logging
from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import prepend_base_command
from cloudinit import util


distros = ['ubuntu']
frequency = PER_INSTANCE

LOG = logging.getLogger(__name__)

schema = {
    'id': 'cc_ubuntu_advantage',
    'name': 'Ubuntu Advantage',
    'title': 'Install, configure and manage ubuntu-advantage offerings',
    'description': dedent("""\
        This module provides configuration options to setup ubuntu-advantage
        subscriptions.

        .. note::
            Both ``commands`` value can be either a dictionary or a list. If
            the configuration provided is a dictionary, the keys are only used
            to order the execution of the commands and the dictionary is
            merged with any vendor-data ubuntu-advantage configuration
            provided. If a ``commands`` is provided as a list, any vendor-data
            ubuntu-advantage ``commands`` are ignored.

        Ubuntu-advantage ``commands`` is a dictionary or list of
        ubuntu-advantage commands to run on the deployed machine.
        These commands can be used to enable or disable subscriptions to
        various ubuntu-advantage products. See 'man ubuntu-advantage' for more
        information on supported subcommands.

        .. note::
           Each command item can be a string or list. If the item is a list,
           'ubuntu-advantage' can be omitted and it will automatically be
           inserted as part of the command.
        """),
    'distros': distros,
    'examples': [dedent("""\
        # Enable Extended Security Maintenance using your service auth token
        ubuntu-advantage:
            commands:
              00: ubuntu-advantage enable-esm <token>
    """), dedent("""\
        # Enable livepatch by providing your livepatch token
        ubuntu-advantage:
            commands:
                00: ubuntu-advantage enable-livepatch <livepatch-token>

    """), dedent("""\
        # Convenience: the ubuntu-advantage command can be omitted when
        # specifying commands as a list and 'ubuntu-advantage' will
        # automatically be prepended.
        # The following commands are equivalent
        ubuntu-advantage:
            commands:
                00: ['enable-livepatch', 'my-token']
                01: ['ubuntu-advantage', 'enable-livepatch', 'my-token']
                02: ubuntu-advantage enable-livepatch my-token
                03: 'ubuntu-advantage enable-livepatch my-token'
    """)],
    'frequency': PER_INSTANCE,
    'type': 'object',
    'properties': {
        'ubuntu-advantage': {
            'type': 'object',
            'properties': {
                'commands': {
                    'type': ['object', 'array'],  # Array of strings or dict
                    'items': {
                        'oneOf': [
                            {'type': 'array', 'items': {'type': 'string'}},
                            {'type': 'string'}]
                    },
                    'additionalItems': False,  # Reject non-string & non-list
                    'minItems': 1,
                    'minProperties': 1,
                }
            },
            'additionalProperties': False,  # Reject keys not in schema
            'required': ['commands']
        }
    }
}

# TODO schema for 'assertions' and 'commands' are too permissive at the moment.
# Once python-jsonschema supports schema draft 6 add support for arbitrary
# object keys with 'patternProperties' constraint to validate string values.

__doc__ = get_schema_doc(schema)  # Supplement python help()

UA_CMD = "ubuntu-advantage"


def run_commands(commands):
    """Run the commands provided in ubuntu-advantage:commands config.

     Commands are run individually. Any errors are collected and reported
     after attempting all commands.

     @param commands: A list or dict containing commands to run. Keys of a
         dict will be used to order the commands provided as dict values.
     """
    if not commands:
        return
    LOG.debug('Running user-provided ubuntu-advantage commands')
    if isinstance(commands, dict):
        # Sort commands based on dictionary key
        commands = [v for _, v in sorted(commands.items())]
    elif not isinstance(commands, list):
        raise TypeError(
            'commands parameter was not a list or dict: {commands}'.format(
                commands=commands))

    fixed_ua_commands = prepend_base_command('ubuntu-advantage', commands)

    cmd_failures = []
    for command in fixed_ua_commands:
        shell = isinstance(command, str)
        try:
            util.subp(command, shell=shell, status_cb=sys.stderr.write)
        except util.ProcessExecutionError as e:
            cmd_failures.append(str(e))
    if cmd_failures:
        msg = (
            'Failures running ubuntu-advantage commands:\n'
            '{cmd_failures}'.format(
                cmd_failures=cmd_failures))
        util.logexc(LOG, msg)
        raise RuntimeError(msg)


def maybe_install_ua_tools(cloud):
    """Install ubuntu-advantage-tools if not present."""
    if util.which('ubuntu-advantage'):
        return
    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(['ubuntu-advantage-tools'])
    except Exception:
        util.logexc(LOG, "Failed to install ubuntu-advantage-tools")
        raise


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('ubuntu-advantage')
    if cfgin is None:
        LOG.debug(("Skipping module named %s,"
                   " no 'ubuntu-advantage' key in configuration"), name)
        return

    validate_cloudconfig_schema(cfg, schema)
    maybe_install_ua_tools(cloud)
    run_commands(cfgin.get('commands', []))

# vi: ts=4 expandtab
