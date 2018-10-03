# This file is part of cloud-init. See LICENSE file for license information.

"""Handle reconfiguration on hotplug events"""
import argparse
import os
import sys

from cloudinit.event import EventType
from cloudinit import log
from cloudinit import reporting
from cloudinit.reporting import events
from cloudinit import sources
from cloudinit.stages import Init
from cloudinit.net import read_sys_net_safe
from cloudinit.net.network_state import parse_net_config_data


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

    parser.add_argument("-d", "--devpath",
                        metavar="PATH",
                        help="sysfs path to hotplugged device")
    parser.add_argument("--hotplug-debug", action='store_true',
                        help='enable debug logging to stderr.')
    parser.add_argument("-s", "--subsystem",
                        choices=['net', 'block'])
    parser.add_argument("-u", "--udevaction",
                        choices=['add', 'change', 'remove'])

    return parser


def log_console(msg):
    """Log messages to stderr console and configured logging."""
    sys.stderr.write(msg + '\n')
    sys.stderr.flush()
    LOG.debug(msg)


def devpath_to_macaddr(devpath):
    macaddr = read_sys_net_safe(os.path.basename(devpath), 'address')
    log_console('Checking if %s in netconfig' % macaddr)
    return macaddr


def in_netconfig(unique_id, netconfig):
    netstate = parse_net_config_data(netconfig)
    found = [iface
             for iface in netstate.iter_interfaces()
             if iface.get('mac_address') == unique_id]
    log_console('Ifaces with ID=%s : %s' % (unique_id, found))
    return len(found) > 0


class UeventHandler(object):
    def __init__(self, ds, devpath, success_fn):
        self.datasource = ds
        self.devpath = devpath
        self.success_fn = success_fn

    def apply(self):
        raise NotImplemented()

    @property
    def config(self):
        raise NotImplemented()

    def detect(self, action):
        raise NotImplemented()

    def success(self):
        return self.success_fn()

    def update(self):
        self.datasource.update_metadata([EventType.UDEV])


class NetHandler(UeventHandler):
    def __init__(self, ds, devpath, success_fn):
        super(NetHandler, self).__init__(ds, devpath, success_fn)
        self.id = devpath_to_macaddr(self.devpath)

    def apply(self):
        return self.datasource.distro.apply_network_config(self.config,
                                                           bring_up=True)

    @property
    def config(self):
        return self.datasource.network_config

    def detect(self, action):
        detect_presence = None
        if action == 'add':
            detect_presence = True
        elif action == 'remove':
            detect_presence = False
        else:
            raise ValueError('Cannot detect unknown action: %s' % action)

        return detect_presence == in_netconfig(self.id, self.config)


UEVENT_HANDLERS = {
    'net': NetHandler,
}

SUBSYSTEM_TO_EVENT = {
    'net': 'network',
    'block': 'storage',
}


def handle_args(name, args):
    log_console('%s called with args=%s' % (NAME, args))
    hotplug_reporter = events.ReportEventStack(NAME, __doc__,
                                               reporting_enabled=True)
    with hotplug_reporter:
        # only handling net udev events for now
        event_handler_cls = UEVENT_HANDLERS.get(args.subsystem)
        if not event_handler_cls:
            log_console('hotplug-hook: cannot handle events for subsystem: '
                        '"%s"' % args.subsystem)
            return 1

        log_console('Reading cloud-init configation')
        hotplug_init = Init(ds_deps=[], reporter=hotplug_reporter)
        hotplug_init.read_cfg()

        log_console('Configuring logging')
        log.setupLogging(hotplug_init.cfg)
        if 'reporting' in hotplug_init.cfg:
            reporting.update_configuration(hotplug_init.cfg.get('reporting'))

        log_console('Fetching datasource')
        try:
            ds = hotplug_init.fetch(existing="trust")
        except sources.DatasourceNotFoundException:
            log_console('No Ds found')
            return 1

        subevent = SUBSYSTEM_TO_EVENT.get(args.subsystem)
        if hotplug_init.update_event_allowed(EventType.UDEV, scope=subevent):
            log_console('cloud-init not configured to handle udev events')
            return

        log_console('Creating %s event handler' % args.subsystem)
        event_handler = event_handler_cls(ds, args.devpath,
                                          hotplug_init._write_to_cache)
        retries = [1, 1, 1, 3, 5]
        for attempt, wait in enumerate(retries):
            log_console('subsystem=%s update attempt %s/%s' % (args.subsystem,
                                                               attempt,
                                                               len(retries)))
            try:
                log_console('Refreshing metadata')
                event_handler.update()
                if event_handler.detect(action=args.udevaction):
                    log_console('Detected update, apply config change')
                    event_handler.apply()
                    log_console('Updating cache')
                    event_handler.success()
                    break
                else:
                    raise Exception(
                            "Failed to detect device change in metadata")

            except Exception as e:
                if attempt + 1 >= len(retries):
                    raise
                log_console('exception while processing hotplug event. %s' % e)

        log_console('exiting handler')
        reporting.flush_events()


if __name__ == '__main__':
    if 'TZ' not in os.environ:
        os.environ['TZ'] = ":/etc/localtime"
    args = get_parser().parse_args()
    handle_args(NAME, args)

# vi: ts=4 expandtab
