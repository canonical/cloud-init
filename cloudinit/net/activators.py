# This file is part of cloud-init. See LICENSE file for license information.
import logging
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Type, Union

from cloudinit import subp, util
from cloudinit.net.eni import available as eni_available
from cloudinit.net.netplan import available as netplan_available
from cloudinit.net.network_manager import available as nm_available
from cloudinit.net.network_state import NetworkState
from cloudinit.net.networkd import available as networkd_available

LOG = logging.getLogger(__name__)


class NoActivatorException(Exception):
    pass


def _alter_interface(cmd, device_name) -> bool:
    LOG.debug("Attempting command %s for device %s", cmd, device_name)
    try:
        (_out, err) = subp.subp(cmd)
        if len(err):
            LOG.warning("Running %s resulted in stderr output: %s", cmd, err)
        return True
    except subp.ProcessExecutionError:
        util.logexc(LOG, "Running interface command %s failed", cmd)
        return False


class NetworkActivator(ABC):
    @staticmethod
    @abstractmethod
    def available(target: Optional[str] = None) -> bool:
        """Return True if activator is available, otherwise return False."""
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up interface.

        Return True is successful, otherwise return False
        """
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def bring_down_interface(device_name: str) -> bool:
        """Bring down interface.

        Return True is successful, otherwise return False
        """
        raise NotImplementedError()

    @classmethod
    def bring_up_interfaces(cls, device_names: Iterable[str]) -> bool:
        """Bring up specified list of interfaces.

        Return True is successful, otherwise return False
        """
        return all(cls.bring_up_interface(device) for device in device_names)

    @classmethod
    def bring_up_all_interfaces(cls, network_state: NetworkState) -> bool:
        """Bring up all interfaces.

        Return True is successful, otherwise return False
        """
        return cls.bring_up_interfaces(
            [i["name"] for i in network_state.iter_interfaces()]
        )


class IfUpDownActivator(NetworkActivator):
    # Note that we're not overriding bring_up_interfaces to pass something
    # like ifup --all because it isn't supported everywhere.
    # E.g., NetworkManager has a ifupdown plugin that requires the name
    # of a specific connection.
    @staticmethod
    def available(target: Optional[str] = None) -> bool:
        """Return true if ifupdown can be used on this system."""
        return eni_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up interface using ifup.

        Return True is successful, otherwise return False
        """
        cmd = ["ifup", device_name]
        return _alter_interface(cmd, device_name)

    @staticmethod
    def bring_down_interface(device_name: str) -> bool:
        """Bring up interface using ifup.

        Return True is successful, otherwise return False
        """
        cmd = ["ifdown", device_name]
        return _alter_interface(cmd, device_name)


class IfConfigActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        """Return true if ifconfig can be used on this system."""
        expected = "ifconfig"
        search = ["/sbin"]
        return subp.which(expected, search=search, target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up interface using ifconfig <dev> up.

        Return True is successful, otherwise return False
        """
        cmd = ["ifconfig", device_name, "up"]
        return _alter_interface(cmd, device_name)

    @staticmethod
    def bring_down_interface(device_name: str) -> bool:
        """Bring up interface using ifconfig <dev> down.

        Return True is successful, otherwise return False
        """
        cmd = ["ifconfig", device_name, "down"]
        return _alter_interface(cmd, device_name)


class NetworkManagerActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        """Return true if NetworkManager can be used on this system."""
        return nm_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up connection using nmcli.

        Return True is successful, otherwise return False
        """
        from cloudinit.net.network_manager import conn_filename

        filename = conn_filename(device_name)
        if filename is None:
            LOG.warning(
                "Unable to find an interface config file. "
                "Unable to bring up interface."
            )
            return False

        cmd = ["nmcli", "connection", "load", filename]
        if _alter_interface(cmd, device_name):
            cmd = ["nmcli", "connection", "up", "filename", filename]
        else:
            _alter_interface(["nmcli", "connection", "reload"], device_name)
            cmd = ["nmcli", "connection", "up", "ifname", device_name]
        return _alter_interface(cmd, device_name)

    @staticmethod
    def bring_down_interface(device_name: str) -> bool:
        """Bring down interface using nmcli.

        Return True is successful, otherwise return False
        """
        cmd = ["nmcli", "device", "disconnect", device_name]
        return _alter_interface(cmd, device_name)


class NetplanActivator(NetworkActivator):
    NETPLAN_CMD = ["netplan", "apply"]

    @staticmethod
    def available(target=None) -> bool:
        """Return true if netplan can be used on this system."""
        return netplan_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Apply netplan config.

        Return True is successful, otherwise return False
        """
        LOG.debug(
            "Calling 'netplan apply' rather than "
            "altering individual interfaces"
        )
        return _alter_interface(NetplanActivator.NETPLAN_CMD, "all")

    @staticmethod
    def bring_up_interfaces(device_names: Iterable[str]) -> bool:
        """Apply netplan config.

        Return True is successful, otherwise return False
        """
        LOG.debug(
            "Calling 'netplan apply' rather than "
            "altering individual interfaces"
        )
        return _alter_interface(NetplanActivator.NETPLAN_CMD, "all")

    @staticmethod
    def bring_up_all_interfaces(network_state: NetworkState) -> bool:
        """Apply netplan config.

        Return True is successful, otherwise return False
        """
        return _alter_interface(NetplanActivator.NETPLAN_CMD, "all")

    @staticmethod
    def bring_down_interface(device_name: str) -> bool:
        """Apply netplan config.

        Return True is successful, otherwise return False
        """
        LOG.debug(
            "Calling 'netplan apply' rather than "
            "altering individual interfaces"
        )
        return _alter_interface(NetplanActivator.NETPLAN_CMD, "all")


class NetworkdActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        """Return true if ifupdown can be used on this system."""
        return networkd_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Return True is successful, otherwise return False"""
        cmd = ["ip", "link", "set", "up", device_name]
        return _alter_interface(cmd, device_name)

    @staticmethod
    def bring_up_all_interfaces(network_state: NetworkState) -> bool:
        """Return True is successful, otherwise return False"""
        cmd = ["systemctl", "restart", "systemd-networkd", "systemd-resolved"]
        return _alter_interface(cmd, "all")

    @staticmethod
    def bring_down_interface(device_name: str) -> bool:
        """Return True is successful, otherwise return False"""
        cmd = ["ip", "link", "set", "down", device_name]
        return _alter_interface(cmd, device_name)


# This section is mostly copied and pasted from renderers.py. An abstract
# version to encompass both seems overkill at this point
DEFAULT_PRIORITY = [
    "eni",
    "netplan",
    "network-manager",
    "networkd",
    "ifconfig",
]

NAME_TO_ACTIVATOR: Dict[str, Type[NetworkActivator]] = {
    "eni": IfUpDownActivator,
    "netplan": NetplanActivator,
    "network-manager": NetworkManagerActivator,
    "networkd": NetworkdActivator,
    "ifconfig": IfConfigActivator,
}


def search_activator(
    priority: List[str], target: Union[str, None]
) -> List[Type[NetworkActivator]]:
    unknown = [i for i in priority if i not in DEFAULT_PRIORITY]
    if unknown:
        raise ValueError(
            "Unknown activators provided in priority list: %s" % unknown
        )
    activator_classes = [NAME_TO_ACTIVATOR[name] for name in priority]
    return [
        activator_cls
        for activator_cls in activator_classes
        if activator_cls.available(target)
    ]


def select_activator(
    priority: Optional[List[str]] = None, target: Optional[str] = None
) -> Type[NetworkActivator]:
    if priority is None:
        priority = DEFAULT_PRIORITY
    found = search_activator(priority, target)
    if not found:
        tmsg = ""
        if target and target != "/":
            tmsg = " in target=%s" % target
        raise NoActivatorException(
            "No available network activators found%s. Searched "
            "through list: %s" % (tmsg, priority)
        )
    selected = found[0]
    LOG.debug(
        "Using selected activator: %s from priority: %s", selected, priority
    )
    return selected
