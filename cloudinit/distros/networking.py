import abc
import logging
import os

from cloudinit import subp
from cloudinit import net, util


LOG = logging.getLogger(__name__)


# Type aliases (https://docs.python.org/3/library/typing.html#type-aliases),
# used to make the signatures of methods a little clearer
DeviceName = str
NetworkConfig = dict


class Networking(metaclass=abc.ABCMeta):
    """The root of the Networking hierarchy in cloud-init.

    This is part of an ongoing refactor in the cloud-init codebase, for more
    details see "``cloudinit.net`` -> ``cloudinit.distros.networking``
    Hierarchy" in HACKING.rst for full details.
    """

    def __init__(self):
        self.blacklist_drivers = None

    def _get_current_rename_info(self) -> dict:
        return net._get_current_rename_info()

    def _rename_interfaces(self, renames: list, *, current_info=None) -> None:
        return net._rename_interfaces(renames, current_info=current_info)

    def apply_network_config_names(self, netcfg: NetworkConfig) -> None:
        return net.apply_network_config_names(netcfg)

    def device_devid(self, devname: DeviceName):
        return net.device_devid(devname)

    def device_driver(self, devname: DeviceName):
        return net.device_driver(devname)

    def extract_physdevs(self, netcfg: NetworkConfig) -> list:
        return net.extract_physdevs(netcfg)

    def find_fallback_nic(self, *, blacklist_drivers=None):
        return net.find_fallback_nic(blacklist_drivers=blacklist_drivers)

    def generate_fallback_config(
        self, *, blacklist_drivers=None, config_driver: bool = False
    ):
        return net.generate_fallback_config(
            blacklist_drivers=blacklist_drivers, config_driver=config_driver
        )

    def get_devicelist(self) -> list:
        return net.get_devicelist()

    def get_ib_hwaddrs_by_interface(self) -> dict:
        return net.get_ib_hwaddrs_by_interface()

    def get_ib_interface_hwaddr(
        self, devname: DeviceName, ethernet_format: bool
    ):
        return net.get_ib_interface_hwaddr(devname, ethernet_format)

    def get_interface_mac(self, devname: DeviceName):
        return net.get_interface_mac(devname)

    def get_interfaces(self) -> list:
        return net.get_interfaces()

    def get_interfaces_by_mac(self) -> dict:
        return net.get_interfaces_by_mac(
            blacklist_drivers=self.blacklist_drivers)

    def get_master(self, devname: DeviceName):
        return net.get_master(devname)

    def interface_has_own_mac(
        self, devname: DeviceName, *, strict: bool = False
    ) -> bool:
        return net.interface_has_own_mac(devname, strict=strict)

    def is_bond(self, devname: DeviceName) -> bool:
        return net.is_bond(devname)

    def is_bridge(self, devname: DeviceName) -> bool:
        return net.is_bridge(devname)

    @abc.abstractmethod
    def is_physical(self, devname: DeviceName) -> bool:
        """
        Is ``devname`` a physical network device?

        Examples of non-physical network devices: bonds, bridges, tunnels,
        loopback devices.
        """

    def is_renamed(self, devname: DeviceName) -> bool:
        return net.is_renamed(devname)

    def is_up(self, devname: DeviceName) -> bool:
        return net.is_up(devname)

    def is_vlan(self, devname: DeviceName) -> bool:
        return net.is_vlan(devname)

    def master_is_bridge_or_bond(self, devname: DeviceName) -> bool:
        return net.master_is_bridge_or_bond(devname)

    @abc.abstractmethod
    def settle(self, *, exists=None) -> None:
        """Wait for device population in the system to complete.

        :param exists:
            An optional optimisation.  If given, only perform as much of the
            settle process as is required for the given DeviceName to be
            present in the system.  (This may include skipping the settle
            process entirely, if the device already exists.)
        :type exists: Optional[DeviceName]
        """

    def wait_for_physdevs(
        self, netcfg: NetworkConfig, *, strict: bool = True
    ) -> None:
        """Wait for all the physical devices in `netcfg` to exist on the system

        Specifically, this will call `self.settle` 5 times, and check after
        each one if the physical devices are now present in the system.

        :param netcfg:
            The NetworkConfig from which to extract physical devices to wait
            for.
        :param strict:
            Raise a `RuntimeError` if any physical devices are not present
            after waiting.
        """
        physdevs = self.extract_physdevs(netcfg)

        # set of expected iface names and mac addrs
        expected_ifaces = dict([(iface[0], iface[1]) for iface in physdevs])
        expected_macs = set(expected_ifaces.keys())

        # set of current macs
        present_macs = self.get_interfaces_by_mac().keys()

        # compare the set of expected mac address values to
        # the current macs present; we only check MAC as cloud-init
        # has not yet renamed interfaces and the netcfg may include
        # such renames.
        for _ in range(0, 5):
            if expected_macs.issubset(present_macs):
                LOG.debug("net: all expected physical devices present")
                return

            missing = expected_macs.difference(present_macs)
            LOG.debug("net: waiting for expected net devices: %s", missing)
            for mac in missing:
                # trigger a settle, unless this interface exists
                devname = expected_ifaces[mac]
                msg = "Waiting for settle or {} exists".format(devname)
                util.log_time(
                    LOG.debug,
                    msg,
                    func=self.settle,
                    kwargs={"exists": devname},
                )

            # update present_macs after settles
            present_macs = self.get_interfaces_by_mac().keys()

        msg = "Not all expected physical devices present: %s" % missing
        LOG.warning(msg)
        if strict:
            raise RuntimeError(msg)

    @abc.abstractmethod
    def try_set_link_up(self, devname: DeviceName) -> bool:
        """Try setting the link to up explicitly and return if it is up."""


class BSDNetworking(Networking):
    """Implementation of networking functionality shared across BSDs."""

    def is_physical(self, devname: DeviceName) -> bool:
        raise NotImplementedError()

    def settle(self, *, exists=None) -> None:
        """BSD has no equivalent to `udevadm settle`; noop."""

    def try_set_link_up(self, devname: DeviceName) -> bool:
        raise NotImplementedError()


class LinuxNetworking(Networking):
    """Implementation of networking functionality common to Linux distros."""

    def get_dev_features(self, devname: DeviceName) -> str:
        return net.get_dev_features(devname)

    def has_netfail_standby_feature(self, devname: DeviceName) -> bool:
        return net.has_netfail_standby_feature(devname)

    def is_netfailover(self, devname: DeviceName) -> bool:
        return net.is_netfailover(devname)

    def is_netfail_master(self, devname: DeviceName) -> bool:
        return net.is_netfail_master(devname)

    def is_netfail_primary(self, devname: DeviceName) -> bool:
        return net.is_netfail_primary(devname)

    def is_netfail_standby(self, devname: DeviceName) -> bool:
        return net.is_netfail_standby(devname)

    def is_physical(self, devname: DeviceName) -> bool:
        return os.path.exists(net.sys_dev_path(devname, "device"))

    def settle(self, *, exists=None) -> None:
        if exists is not None:
            exists = net.sys_dev_path(exists)
        util.udevadm_settle(exists=exists)

    def try_set_link_up(self, devname: DeviceName) -> bool:
        """Try setting the link to up explicitly and return if it is up.
           Not guaranteed to bring the interface up. The caller is expected to
           add wait times before retrying."""
        subp.subp(['ip', 'link', 'set', devname, 'up'])
        return self.is_up(devname)
