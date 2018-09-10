# This file is part of cloud-init. See LICENSE file for license information.

"""Handle reconfiguration on hotplug events"""
import argparse
import os

from cloudinit.event import EventType
from cloudinit import log
from cloudinit import reporting
from cloudinit import sources
from cloudinit.reporting import events
from cloudinit.stages import Init

LOG = log.getLogger(__name__)
NAME = 'hotplug-hook'


def get_parser(parser=None):
    """Build or extend and arg parser for hotplug-hook utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    return parser


def load_udev_environment():
    print('loading os environment')
    return os.environ.copy()


def handle_args(name, args):
    if args.debug:
        log.setupBasicLogging(level=log.DEBUG)
    else:
        log.setupBasicLogging(level=log.WARN)

    hotplug_reporter = events.ReportEventStack(NAME, __doc__,
                                               reporting_enabled=True)
    with hotplug_reporter:
        env = load_udev_environment()
        udev_subsystem = env.get('SUBSYSTEM')

        # only handling net udev events for now
        if udev_subsystem not in ['net']:
            LOG.warn('hotplug-hook: cannot handle events for subsystem: "%s"',
                     udev_subsystem)
            return 0

        hotplug_init = Init(ds_deps=[], reporter=hotplug_reporter)
        hotplug_init.read_cfg()
        try:
            ds = hotplug_init.fetch(existing="trust")
        except sources.DatasourceNotFoundException:
            print('No Ds found')
            return 1

        # refresh metadata
        print('requesting metadata refresh for EventType.UDEV')
        ds.update_metadata([EventType.UDEV])

        print('Update instance datasource cache')
        hotplug_init._write_to_cache()

        if udev_subsystem == 'net':
            # apply network config
            netcfg = ds.network_config
            print('Calling distro.apply_network_config with updated netcfg')
            ds.distro.apply_network_config(netcfg, bring_up=True)

        print('hotplug-hook exit')
        reporting.flush_events()


if __name__ == '__main__':
    if 'TZ' not in os.environ:
        os.environ['TZ'] = ":/etc/localtime"
    args = get_parser().parse_args()
    handle_args(NAME, args)

# vi: ts=4 expandtab
