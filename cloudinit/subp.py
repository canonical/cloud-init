# This file is part of cloud-init. See LICENSE file for license information.
"""Common utility functions for interacting with subprocess."""

# TODO move subp shellify and runparts related functions out of util.py

import logging

LOG = logging.getLogger(__name__)


def prepend_base_command(base_command, commands):
    """Ensure user-provided commands start with base_command; warn otherwise.

    Each command is either a list or string. Perform the following:
       - If the command is a list, pop the first element if it is None
       - If the command is a list, insert base_command as the first element if
         not present.
       - When the command is a string not starting with 'base-command', warn.

    Allow flexibility to provide non-base-command environment/config setup if
    needed.

    @commands: List of commands. Each command element is a list or string.

    @return: List of 'fixed up' commands.
    @raise: TypeError on invalid config item type.
    """
    warnings = []
    errors = []
    fixed_commands = []
    for command in commands:
        if isinstance(command, list):
            if command[0] is None:  # Avoid warnings by specifying None
                command = command[1:]
            elif command[0] != base_command:  # Automatically prepend
                command.insert(0, base_command)
        elif isinstance(command, str):
            if not command.startswith('%s ' % base_command):
                warnings.append(command)
        else:
            errors.append(str(command))
            continue
        fixed_commands.append(command)

    if warnings:
        LOG.warning(
            'Non-%s commands in %s config:\n%s',
            base_command, base_command, '\n'.join(warnings))
    if errors:
        raise TypeError(
            'Invalid {name} config.'
            ' These commands are not a string or list:\n{errors}'.format(
                name=base_command, errors='\n'.join(errors)))
    return fixed_commands


# vi: ts=4 expandtab
