# This file is part of cloud-init. See LICENSE file for license information.

"""Run the dhclient hook to record network info."""

import argparse
import os

from cloudinit import atomic_helper
from cloudinit import log as logging
from cloudinit import stages

LOG = logging.getLogger(__name__)

NAME = "dhclient-hook"
UP = "up"
DOWN = "down"
EVENTS = (UP, DOWN)


def _get_hooks_dir():
    i = stages.Init()
    return os.path.join(i.paths.get_runpath(), 'dhclient.hooks')


def _filter_env_vals(info):
    """Given info (os.environ), return a dictionary with
    lower case keys for each entry starting with DHCP4_ or new_."""
    new_info = {}
    for k, v in info.items():
        if k.startswith("DHCP4_") or k.startswith("new_"):
            key = (k.replace('DHCP4_', '').replace('new_', '')).lower()
            new_info[key] = v
    return new_info


def run_hook(interface, event, data_d=None, env=None):
    if event not in EVENTS:
        raise ValueError("Unexpected event '%s'. Expected one of: %s" %
                         (event, EVENTS))
    if data_d is None:
        data_d = _get_hooks_dir()
    if env is None:
        env = os.environ
    hook_file = os.path.join(data_d, interface + ".json")

    if event == UP:
        if not os.path.exists(data_d):
            os.makedirs(data_d)
        atomic_helper.write_json(hook_file, _filter_env_vals(env))
        LOG.debug("Wrote dhclient options in %s", hook_file)
    elif event == DOWN:
        if os.path.exists(hook_file):
            os.remove(hook_file)
            LOG.debug("Removed dhclient options file %s", hook_file)


def get_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        "event", help='event taken on the interface', choices=EVENTS)
    parser.add_argument(
        "interface", help='the network interface being acted upon')
    # cloud-init main uses 'action'
    parser.set_defaults(action=(NAME, handle_args))
    return parser


def handle_args(name, args, data_d=None):
    """Handle the Namespace args.
    Takes 'name' as passed by cloud-init main. not used here."""
    return run_hook(interface=args.interface, event=args.event, data_d=data_d)


if __name__ == '__main__':
    import sys
    parser = get_parser()
    args = parser.parse_args(args=sys.argv[1:])
    return_value = handle_args(
        NAME, args, data_d=os.environ.get('_CI_DHCP_HOOK_DATA_D'))
    if return_value:
        sys.exit(return_value)


# vi: ts=4 expandtab
