import abc

from cloudinit import net


# Type aliases, used to make the signatures of methods a little clearer
DeviceName = str
NetworkConfig = dict


class Networking(metaclass=abc.ABCMeta):
    """The root of tne Networking hierarchy in cloud-init.

    This is part of an ongoing refactor in the cloud-init codebase, for more
    details see "``cloudinit.net`` -> ``cloudinit.distros.networking``
    Hierarchy" in HACKING.rst for full details.
    """
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
        self, ifname: DeviceName, ethernet_format: bool
    ):
        return net.get_ib_interface_hwaddr(ifname, ethernet_format)

    def get_interface_mac(self, ifname: DeviceName):
        return net.get_interface_mac(ifname)

    def get_interfaces(self) -> list:
        return net.get_interfaces()

    def get_interfaces_by_mac(self) -> dict:
        return net.get_interfaces_by_mac()

    def get_master(self, devname: DeviceName):
        return net.get_master(devname)

    def interface_has_own_mac(
        self, ifname: DeviceName, *, strict: bool = False
    ) -> bool:
        return net.interface_has_own_mac(ifname, strict=strict)

    def is_bond(self, devname: DeviceName) -> bool:
        return net.is_bond(devname)

    def is_bridge(self, devname: DeviceName) -> bool:
        return net.is_bridge(devname)

    def is_connected(self, devname: DeviceName) -> bool:
        return net.is_connected(devname)

    def is_physical(self, devname: DeviceName) -> bool:
        return net.is_physical(devname)

    def is_present(self, devname: DeviceName) -> bool:
        return net.is_present(devname)

    def is_renamed(self, devname: DeviceName) -> bool:
        return net.is_renamed(devname)

    def is_up(self, devname: DeviceName) -> bool:
        return net.is_up(devname)

    def is_vlan(self, devname: DeviceName) -> bool:
        return net.is_vlan(devname)

    def is_wireless(self, devname: DeviceName) -> bool:
        return net.is_wireless(devname)

    def master_is_bridge_or_bond(self, devname: DeviceName) -> bool:
        return net.master_is_bridge_or_bond(devname)

    def wait_for_physdevs(
        self, netcfg: NetworkConfig, *, strict: bool = True
    ) -> None:
        return net.wait_for_physdevs(netcfg, strict=strict)


class BSDNetworking(Networking):

    pass


class LinuxNetworking(Networking):
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
