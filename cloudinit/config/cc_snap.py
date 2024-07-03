# Copyright (C) 2018 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Snap: Install, configure and manage snapd and snap packages."""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import prepend_base_command

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_snap",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["snap"],
}  # type: ignore

SNAP_CMD = "snap"


def add_assertions(assertions, assertions_file):
    r"""Import list of assertions.

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
    util.wait_for_snap_seeded(cloud)
    add_assertions(
        cfgin.get("assertions", []),
        os.path.join(cloud.paths.get_ipath_cur(), "snapd.assertions"),
    )
    run_commands(cfgin.get("commands", []))
