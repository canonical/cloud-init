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
    parser.add_argument("--debug", action='store_true',
                        help='enable debug logging to stderr.')
    parser.add_argument("-s", "--subsystem",
                        choices=['net', 'block'])
    parser.add_argument("-u", "--udevaction",
                        choices=['add', 'change', 'remove'])
    parser.add_argument('-i', '--input', metavar="PATH",
                        help='read arguments from stdin or file')

    return parser


def load_udev_environment():
    print('loading os environment')
    return os.environ.copy()


def devpath_to_macaddr(devpath):
    macaddr = read_sys_net_safe(os.path.basename(devpath), 'address')
    LOG.debug('Checking if %s in netconfig', macaddr)
    return macaddr


def in_netconfig(unique_id, netconfig):
    netstate = parse_net_config_data(netconfig)
    found = [iface
             for iface in netstate.iter_interfaces()
             if iface.get('mac_address') == unique_id]
    LOG.debug('Ifaces with ID=%s : %s', unique_id, found)
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


def handle_args(name, args):
    # handle args from stdin (udev hotplug hook)
    if args.input:
        if args.input == '-':
            reader = sys.stdin
        else:
            reader = open(args.input, 'r')
        # parse input for args
        reader_input = reader.read().split()
        args = get_parser().parse_args(reader_input)

    if args.debug:
        LOG.setLevel(level=log.DEBUG)
    else:
        LOG.setLevel(level=log.WARN)

    hotplug_reporter = events.ReportEventStack(NAME, __doc__,
                                               reporting_enabled=True)
    with hotplug_reporter:
        # only handling net udev events for now
        event_handler_cls = UEVENT_HANDLERS.get(args.subsystem)
        if not event_handler_cls:
            LOG.warn('hotplug-hook: cannot handle events for subsystem: "%s"',
                     args.subsystem)
            return 1

        # read cloud-init config and configure logging
        hotplug_init = Init(ds_deps=[], reporter=hotplug_reporter)
        hotplug_init.read_cfg()
        log.setupLogging(hotplug_init.cfg)
        if 'reporting' in hotplug_init.cfg:
            reporting.update_configuration(hotplug_init.cfg.get('reporting'))

        # load datasource from cache
        try:
            ds = hotplug_init.fetch(existing="trust")
        except sources.DatasourceNotFoundException:
            print('No Ds found')
            return 1

        event_handler = event_handler_cls(ds, args.devpath,
                                          hotplug_init._write_to_cache)
        retries = [1, 1, 1, 3, 5]
        for attempt, wait in enumerate(retries):
            LOG.debug('Hotplug hook subsystem=%s attempt %s/%s',
                      args.subsystem, attempt, len(retries))
            try:
                event_handler.update()
                if event_handler.detect(action=args.udevaction):
                    event_handler.apply()
                    event_handler.success()
                    break
                else:
                    raise Exception(
                            "Failed to detect device change in metadata")

            except Exception as e:
                if attempt + 1 >= len(retries):
                    raise
                LOG.debug('exception while processing hotplug event. %s', e)

        print('hotplug-hook exit')
        reporting.flush_events()


if __name__ == '__main__':
    if 'TZ' not in os.environ:
        os.environ['TZ'] = ":/etc/localtime"
    args = get_parser().parse_args()
    handle_args(NAME, args)

# vi: ts=4 expandtab
