# Copyright (C) 2018 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Snap: Install, configure and manage snapd and snap packages."""

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
    'id': 'cc_snap',
    'name': 'Snap',
    'title': 'Install, configure and manage snapd and snap packages',
    'description': dedent("""\
        This module provides a simple configuration namespace in cloud-init to
        both setup snapd and install snaps.

        .. note::
            Both ``assertions`` and ``commands`` values can be either a
            dictionary or a list. If these configs are provided as a
            dictionary, the keys are only used to order the execution of the
            assertions or commands and the dictionary is merged with any
            vendor-data snap configuration provided. If a list is provided by
            the user instead of a dict, any vendor-data snap configuration is
            ignored.

        The ``assertions`` configuration option is a dictionary or list of
        properly-signed snap assertions which will run before any snap
        ``commands``. They will be added to snapd's assertion database by
        invoking ``snap ack <aggregate_assertion_file>``.

        Snap ``commands`` is a dictionary or list of individual snap
        commands to run on the target system. These commands can be used to
        create snap users, install snaps and provide snap configuration.

        .. note::
            If 'side-loading' private/unpublished snaps on an instance, it is
            best to create a snap seed directory and seed.yaml manifest in
            **/var/lib/snapd/seed/** which snapd automatically installs on
            startup.

        **Development only**: The ``squashfuse_in_container`` boolean can be
        set true to install squashfuse package when in a container to enable
        snap installs. Default is false.
        """),
    'distros': distros,
    'examples': [dedent("""\
        snap:
            assertions:
              00: |
              signed_assertion_blob_here
              02: |
              signed_assertion_blob_here
            commands:
              00: snap create-user --sudoer --known <snap-user>@mydomain.com
              01: snap install canonical-livepatch
              02: canonical-livepatch enable <AUTH_TOKEN>
    """), dedent("""\
        # LXC-based containers require squashfuse before snaps can be installed
        snap:
            commands:
                00: apt-get install squashfuse -y
                11: snap install emoj

    """), dedent("""\
        # Convenience: the snap command can be omitted when specifying commands
        # as a list and 'snap' will automatically be prepended.
        # The following commands are equivalent:
        snap:
            commands:
                00: ['install', 'vlc']
                01: ['snap', 'install', 'vlc']
                02: snap install vlc
                03: 'snap install vlc'
    """)],
    'frequency': PER_INSTANCE,
    'type': 'object',
    'properties': {
        'snap': {
            'type': 'object',
            'properties': {
                'assertions': {
                    'type': ['object', 'array'],  # Array of strings or dict
                    'items': {'type': 'string'},
                    'additionalItems': False,  # Reject items non-string
                    'minItems': 1,
                    'minProperties': 1,
                    'uniqueItems': True
                },
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
                },
                'squashfuse_in_container': {
                    'type': 'boolean'
                }
            },
            'additionalProperties': False,  # Reject keys not in schema
            'required': [],
            'minProperties': 1
        }
    }
}

# TODO schema for 'assertions' and 'commands' are too permissive at the moment.
# Once python-jsonschema supports schema draft 6 add support for arbitrary
# object keys with 'patternProperties' constraint to validate string values.

__doc__ = get_schema_doc(schema)  # Supplement python help()

SNAP_CMD = "snap"
ASSERTIONS_FILE = "/var/lib/cloud/instance/snapd.assertions"


def add_assertions(assertions):
    """Import list of assertions.

    Import assertions by concatenating each assertion into a
    string separated by a '\n'.  Write this string to a instance file and
    then invoke `snap ack /path/to/file` and check for errors.
    If snap exits 0, then all assertions are imported.
    """
    if not assertions:
        return
    LOG.debug('Importing user-provided snap assertions')
    if isinstance(assertions, dict):
        assertions = assertions.values()
    elif not isinstance(assertions, list):
        raise TypeError(
            'assertion parameter was not a list or dict: {assertions}'.format(
                assertions=assertions))

    snap_cmd = [SNAP_CMD, 'ack']
    combined = "\n".join(assertions)

    for asrt in assertions:
        LOG.debug('Snap acking: %s', asrt.split('\n')[0:2])

    util.write_file(ASSERTIONS_FILE, combined.encode('utf-8'))
    util.subp(snap_cmd + [ASSERTIONS_FILE], capture=True)


def run_commands(commands):
    """Run the provided commands provided in snap:commands configuration.

     Commands are run individually. Any errors are collected and reported
     after attempting all commands.

     @param commands: A list or dict containing commands to run. Keys of a
         dict will be used to order the commands provided as dict values.
     """
    if not commands:
        return
    LOG.debug('Running user-provided snap commands')
    if isinstance(commands, dict):
        # Sort commands based on dictionary key
        commands = [v for _, v in sorted(commands.items())]
    elif not isinstance(commands, list):
        raise TypeError(
            'commands parameter was not a list or dict: {commands}'.format(
                commands=commands))

    fixed_snap_commands = prepend_base_command('snap', commands)

    cmd_failures = []
    for command in fixed_snap_commands:
        shell = isinstance(command, str)
        try:
            util.subp(command, shell=shell, status_cb=sys.stderr.write)
        except util.ProcessExecutionError as e:
            cmd_failures.append(str(e))
    if cmd_failures:
        msg = 'Failures running snap commands:\n{cmd_failures}'.format(
            cmd_failures=cmd_failures)
        util.logexc(LOG, msg)
        raise RuntimeError(msg)


# RELEASE_BLOCKER: Once LP: #1628289 is released on xenial, drop this function.
def maybe_install_squashfuse(cloud):
    """Install squashfuse if we are in a container."""
    if not util.is_container():
        return
    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(['squashfuse'])
    except Exception:
        util.logexc(LOG, "Failed to install squashfuse")
        raise


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('snap', {})
    if not cfgin:
        LOG.debug(("Skipping module named %s,"
                   " no 'snap' key in configuration"), name)
        return

    validate_cloudconfig_schema(cfg, schema)
    if util.is_true(cfgin.get('squashfuse_in_container', False)):
        maybe_install_squashfuse(cloud)
    add_assertions(cfgin.get('assertions', []))
    run_commands(cfgin.get('commands', []))

# vi: ts=4 expandtab
