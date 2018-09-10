# This file is part of cloud-init. See LICENSE file for license information.

"""Handle reconfiguration on hotplug events"""
import argparse
import os

from cloudinit.event import EventType
from cloudinit.stages import _pkl_load
from cloudinit import log

LOG = log.getLogger(__name__)
NAME = 'hotplug-hook'
OBJ_PKL = "/var/lib/cloud/instance/obj.pkl"


def get_parser(parser=None):
    """Build or extend and arg parser for hotplug-hook utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    return parser


def load_cloud_object(object_path=OBJ_PKL):
    print('loading object %s' % object_path)
    return _pkl_load(object_path)


def load_udev_environment():
    print('loading os environment')
    return os.environ.copy()


def handle_args(name, args):
    if args.debug:
        log.setupBasicLogging(level=log.DEBUG)
    else:
        log.setupBasicLogging(level=log.WARN)

    env = load_udev_environment()
    udev_subsystem = env.get('SUBSYSTEM')

    if udev_subsystem not in ['net']:
        LOG.warn('hotplug-hook: cannot handle events for subsystem: "%s"',
                 udev_subsystem)
        return 0

    # load instance object pkl
    cloud_obj = load_cloud_object()

    # refresh metadata
    print('requesting metadata refresh for EventType.UDEV')
    cloud_obj.update_metadata([EventType.UDEV])

    if udev_subsystem == 'net':
        # apply network config
        netcfg = cloud_obj.network_config
        print('Calling distro.apply_network_config with updated netcfg')
        cloud_obj.distro.apply_network_config(netcfg, bring_up=True)

    print('hotplug-hook exit')


if __name__ == '__main__':
    args = get_parser().parse_args()
    handle_args(NAME, args)

# vi: ts=4 expandtab
