# Copyright (C) 2018 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Snap: Install, configure and manage snapd and snap packages."""

import logging
import os
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import prepend_base_command

distros = ["ubuntu"]
frequency = PER_INSTANCE

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_snap",
    "name": "Snap",
    "title": "Install, configure and manage snapd and snap packages",
    "description": dedent(
        """\
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
        """
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
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
    """
        ),
        dedent(
            """\
        # Convenience: the snap command can be omitted when specifying commands
        # as a list and 'snap' will automatically be prepended.
        # The following commands are equivalent:
        snap:
          commands:
            00: ['install', 'vlc']
            01: ['snap', 'install', 'vlc']
            02: snap install vlc
            03: 'snap install vlc'
    """
        ),
        dedent(
            """\
        # You can use a list of commands
        snap:
          commands:
            - ['install', 'vlc']
            - ['snap', 'install', 'vlc']
            - snap install vlc
            - 'snap install vlc'
    """
        ),
        dedent(
            """\
        # You can use a list of assertions
        snap:
          assertions:
            - signed_assertion_blob_here
            - |
              signed_assertion_blob_here
    """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["snap"],
}


__doc__ = get_meta_doc(meta)

SNAP_CMD = "snap"


def add_assertions(assertions, assertions_file):
    """Import list of assertions.

    Import assertions by concatenating each assertion into a
    string separated by a '\n'.  Write this string to a instance file and
    then invoke `snap ack /path/to/file` and check for errors.
    If snap exits 0, then all assertions are imported.
    """
    if not assertions:
        return
    LOG.debug("Importing user-provided snap assertions")
    if isinstance(assertions, dict):
        assertions = assertions.values()
    elif not isinstance(assertions, list):
        raise TypeError(
            "assertion parameter was not a list or dict: {assertions}".format(
                assertions=assertions
            )
        )

    snap_cmd = [SNAP_CMD, "ack", assertions_file]
    combined = "\n".join(assertions)

    for asrt in assertions:
        LOG.debug("Snap acking: %s", asrt.split("\n")[0:2])

    util.write_file(assertions_file, combined.encode("utf-8"))
    subp.subp(snap_cmd, capture=True)


def run_commands(commands):
    """Run the provided commands provided in snap:commands configuration.

    Commands are run individually. Any errors are collected and reported
    after attempting all commands.

    @param commands: A list or dict containing commands to run. Keys of a
        dict will be used to order the commands provided as dict values.
    """
    if not commands:
        return
    LOG.debug("Running user-provided snap commands")
    if isinstance(commands, dict):
        # Sort commands based on dictionary key
        commands = [v for _, v in sorted(commands.items())]
    elif not isinstance(commands, list):
        raise TypeError(
            "commands parameter was not a list or dict: {commands}".format(
                commands=commands
            )
        )

    fixed_snap_commands = prepend_base_command("snap", commands)

    cmd_failures = []
    for command in fixed_snap_commands:
        shell = isinstance(command, str)
        try:
            subp.subp(command, shell=shell)
        except subp.ProcessExecutionError as e:
            cmd_failures.append(str(e))
    if cmd_failures:
        msg = "Failures running snap commands:\n{cmd_failures}".format(
            cmd_failures=cmd_failures
        )
        util.logexc(LOG, msg)
        raise RuntimeError(msg)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    cfgin = cfg.get("snap", {})
    if not cfgin:
        LOG.debug(
            "Skipping module named %s, no 'snap' key in configuration", name
        )
        return

    add_assertions(
        cfgin.get("assertions", []),
        os.path.join(cloud.paths.get_ipath_cur(), "snapd.assertions"),
    )
    run_commands(cfgin.get("commands", []))
