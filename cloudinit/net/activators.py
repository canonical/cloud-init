# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
from abc import ABC, abstractmethod
from typing import Iterable, List, Type

from cloudinit import subp
from cloudinit import util
from cloudinit.net.eni import available as eni_available
from cloudinit.net.netplan import available as netplan_available
from cloudinit.net.network_state import NetworkState
from cloudinit.net.sysconfig import NM_CFG_FILE


LOG = logging.getLogger(__name__)


class NetworkActivator(ABC):
    @staticmethod
    @abstractmethod
    def available() -> bool:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def bring_up_interface(device_name: str) -> bool:
        raise NotImplementedError()

    @classmethod
    def bring_up_interfaces(cls, device_names: Iterable[str]) -> bool:
        all_succeeded = True
        for device in device_names:
            if not cls.bring_up_interface(device):
                all_succeeded = False
        return all_succeeded

    @classmethod
    def bring_up_all_interfaces(cls, network_state: NetworkState) -> bool:
        return cls.bring_up_interfaces(
            [i['name'] for i in network_state.iter_interfaces()]
        )


class IfUpDownActivator(NetworkActivator):
    # Note that we're not overriding bring_up_interfaces to pass something
    # like ifup --all because it isn't supported everywhere.
    # E.g., NetworkManager has a ifupdown plugin that requires the name
    # of a specific connection.
    @staticmethod
    def available(target=None) -> bool:
        """Return true if ifupdown can be used on this system."""
        return eni_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up interface using ifup."""
        cmd = ['ifup', device_name]
        LOG.debug("Attempting to run bring up interface %s using command %s",
                  device_name, cmd)
        try:
            (_out, err) = subp.subp(cmd)
            if len(err):
                LOG.warning("Running %s resulted in stderr output: %s",
                            cmd, err)
            return True
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False


class NetworkManagerActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        config_present = os.path.isfile(
            subp.target_path(target, path=NM_CFG_FILE)
        )
        nmcli_present = subp.which('nmcli', target=target)
        return config_present and bool(nmcli_present)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        try:
            subp.subp(['nmcli', 'connection', 'up', device_name])
        except subp.ProcessExecutionError:
            util.logexc(LOG, "nmcli failed to bring up {}".format(device_name))
            return False
        return True


class NetplanActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        return netplan_available(target=target)

    @staticmethod
    def _apply_netplan():
        LOG.debug('Applying current netplan config')
        try:
            subp.subp(['netplan', 'apply'], capture=True)
        except subp.ProcessExecutionError:
            util.logexc(LOG, "netplan apply failed")
            return False
        return True

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        LOG.debug("Calling 'netplan apply' rather than "
                  "bringing up individual interfaces")
        return NetplanActivator._apply_netplan()

    @staticmethod
    def bring_up_interfaces(device_names: Iterable[str]) -> bool:
        LOG.debug("Calling 'netplan apply' rather than "
                  "bringing up individual interfaces")
        return NetplanActivator._apply_netplan()

    @staticmethod
    def bring_up_all_interfaces(network_state: NetworkState) -> bool:
        return NetplanActivator._apply_netplan()


# This section is mostly copied and pasted from renderers.py. An abstract
# version to encompass both seems overkill at this point
DEFAULT_PRIORITY = [
    IfUpDownActivator,
    NetworkManagerActivator,
    NetplanActivator,
]


def search_activator(
    priority=None, target=None
) -> List[Type[NetworkActivator]]:
    if priority is None:
        priority = DEFAULT_PRIORITY

    unknown = [i for i in priority if i not in DEFAULT_PRIORITY]
    if unknown:
        raise ValueError(
            "Unknown activators provided in priority list: %s" % unknown)

    return [activator for activator in priority if activator.available(target)]


def select_activator(priority=None, target=None) -> Type[NetworkActivator]:
    found = search_activator(priority, target)
    if not found:
        if priority is None:
            priority = DEFAULT_PRIORITY
        tmsg = ""
        if target and target != "/":
            tmsg = " in target=%s" % target
        raise RuntimeError(
            "No available network activators found%s. Searched "
            "through list: %s" % (tmsg, priority))
    return found[0]
