#!/usr/bin/env python3

# This file is part of cloud-init. See LICENSE file for license information.
"""Handle reconfiguration on hotplug events."""
import abc
import argparse
import os
import sys
import time

from cloudinit import log, reporting, stages
from cloudinit.event import EventScope, EventType
from cloudinit.net import read_sys_net_safe
from cloudinit.net.network_state import parse_net_config_data
from cloudinit.reporting import events
from cloudinit.sources import DataSource, DataSourceNotFoundException
from cloudinit.stages import Init

LOG = log.getLogger(__name__)
NAME = "hotplug-hook"


def get_parser(parser=None):
    """Build or extend an arg parser for hotplug-hook utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)

    parser.description = __doc__
    parser.add_argument(
        "-s",
        "--subsystem",
        required=True,
        help="subsystem to act on",
        choices=["net"],
    )

    subparsers = parser.add_subparsers(
        title="Hotplug Action", dest="hotplug_action"
    )
    subparsers.required = True

    subparsers.add_parser(
        "query", help="Query if hotplug is enabled for given subsystem."
    )

    parser_handle = subparsers.add_parser(
        "handle", help="Handle the hotplug event."
    )
    parser_handle.add_argument(
        "-d",
        "--devpath",
        required=True,
        metavar="PATH",
        help="Sysfs path to hotplugged device",
    )
    parser_handle.add_argument(
        "-u",
        "--udevaction",
        required=True,
        help="Specify action to take.",
        choices=["add", "remove"],
    )

    return parser


class UeventHandler(abc.ABC):
    def __init__(self, id, datasource, devpath, action, success_fn):
        self.id = id
        self.datasource: DataSource = datasource
        self.devpath = devpath
        self.action = action
        self.success_fn = success_fn

    @abc.abstractmethod
    def apply(self):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def config(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def device_detected(self) -> bool:
        raise NotImplementedError()

    def detect_hotplugged_device(self):
        detect_presence = None
        if self.action == "add":
            detect_presence = True
        elif self.action == "remove":
            detect_presence = False
        else:
            raise ValueError("Unknown action: %s" % self.action)

        if detect_presence != self.device_detected():
            raise RuntimeError(
                "Failed to detect %s in updated metadata" % self.id
            )

    def success(self):
        return self.success_fn()

    def update_metadata(self):
        result = self.datasource.update_metadata_if_supported(
            [EventType.HOTPLUG]
        )
        if not result:
            raise RuntimeError(
                "Datasource %s not updated for event %s"
                % (self.datasource, EventType.HOTPLUG)
            )
        return result


class NetHandler(UeventHandler):
    def __init__(self, datasource, devpath, action, success_fn):
        # convert devpath to mac address
        id = read_sys_net_safe(os.path.basename(devpath), "address")
        super().__init__(id, datasource, devpath, action, success_fn)

    def apply(self):
        self.datasource.distro.apply_network_config(
            self.config,
            bring_up=False,
        )
        interface_name = os.path.basename(self.devpath)
        activator = self.datasource.distro.network_activator()
        if self.action == "add":
            if not activator.bring_up_interface(interface_name):
                raise RuntimeError(
                    "Failed to bring up device: {}".format(self.devpath)
                )
        elif self.action == "remove":
            if not activator.bring_down_interface(interface_name):
                raise RuntimeError(
                    "Failed to bring down device: {}".format(self.devpath)
                )

    @property
    def config(self):
        return self.datasource.network_config

    def device_detected(self) -> bool:
        netstate = parse_net_config_data(self.config)
        found = [
            iface
            for iface in netstate.iter_interfaces()
            if iface.get("mac_address") == self.id
        ]
        LOG.debug("Ifaces with ID=%s : %s", self.id, found)
        return len(found) > 0


SUBSYSTEM_PROPERTES_MAP = {
    "net": (NetHandler, EventScope.NETWORK),
}


def is_enabled(hotplug_init, subsystem):
    try:
        scope = SUBSYSTEM_PROPERTES_MAP[subsystem][1]
    except KeyError as e:
        raise Exception(
            "hotplug-hook: cannot handle events for subsystem: {}".format(
                subsystem
            )
        ) from e

    return stages.update_event_enabled(
        datasource=hotplug_init.datasource,
        cfg=hotplug_init.cfg,
        event_source_type=EventType.HOTPLUG,
        scope=scope,
    )


def initialize_datasource(hotplug_init: Init, subsystem: str):
    LOG.debug("Fetching datasource")
    datasource = hotplug_init.fetch(existing="trust")

    if not datasource.get_supported_events([EventType.HOTPLUG]):
        LOG.debug("hotplug not supported for event of type %s", subsystem)
        return

    if not is_enabled(hotplug_init, subsystem):
        LOG.debug("hotplug not enabled for event of type %s", subsystem)
        return
    return datasource


def handle_hotplug(hotplug_init: Init, devpath, subsystem, udevaction):
    datasource = initialize_datasource(hotplug_init, subsystem)
    if not datasource:
        return
    handler_cls = SUBSYSTEM_PROPERTES_MAP[subsystem][0]
    LOG.debug("Creating %s event handler", subsystem)
    event_handler: UeventHandler = handler_cls(
        datasource=datasource,
        devpath=devpath,
        action=udevaction,
        success_fn=hotplug_init._write_to_cache,
    )
    wait_times = [1, 3, 5, 10, 30]
    last_exception = Exception("Bug while processing hotplug event.")
    for attempt, wait in enumerate(wait_times):
        LOG.debug(
            "subsystem=%s update attempt %s/%s",
            subsystem,
            attempt,
            len(wait_times),
        )
        try:
            LOG.debug("Refreshing metadata")
            event_handler.update_metadata()
            if not datasource.skip_hotplug_detect:
                LOG.debug("Detecting device in updated metadata")
                event_handler.detect_hotplugged_device()
            LOG.debug("Applying config change")
            event_handler.apply()
            LOG.debug("Updating cache")
            event_handler.success()
            break
        except Exception as e:
            LOG.debug("Exception while processing hotplug event. %s", e)
            time.sleep(wait)
            last_exception = e
    else:
        raise last_exception


def handle_args(name, args):
    # Note that if an exception happens between now and when logging is
    # setup, we'll only see it in the journal
    hotplug_reporter = events.ReportEventStack(
        name, __doc__, reporting_enabled=True
    )

    hotplug_init = Init(ds_deps=[], reporter=hotplug_reporter)
    hotplug_init.read_cfg()

    log.setupLogging(hotplug_init.cfg)
    if "reporting" in hotplug_init.cfg:
        reporting.update_configuration(hotplug_init.cfg.get("reporting"))
    # Logging isn't going to be setup until now
    LOG.debug(
        "%s called with the following arguments: {"
        "hotplug_action: %s, subsystem: %s, udevaction: %s, devpath: %s}",
        name,
        args.hotplug_action,
        args.subsystem,
        args.udevaction if "udevaction" in args else None,
        args.devpath if "devpath" in args else None,
    )

    with hotplug_reporter:
        try:
            if args.hotplug_action == "query":
                try:
                    datasource = initialize_datasource(
                        hotplug_init, args.subsystem
                    )
                except DataSourceNotFoundException:
                    print(
                        "Unable to determine hotplug state. No datasource "
                        "detected"
                    )
                    sys.exit(1)
                print("enabled" if datasource else "disabled")
            else:
                handle_hotplug(
                    hotplug_init=hotplug_init,
                    devpath=args.devpath,
                    subsystem=args.subsystem,
                    udevaction=args.udevaction,
                )
        except Exception:
            LOG.exception("Received fatal exception handling hotplug!")
            raise

    LOG.debug("Exiting hotplug handler")
    reporting.flush_events()


if __name__ == "__main__":
    args = get_parser().parse_args()
    handle_args(NAME, args)
