# This file is part of cloud-init. See LICENSE file for license information.

# This file is mostly copied and pasted from renderers.py. An abstract
# version to encompass both seems overkill at this point
from typing import List, Type

from cloudinit.net.configurer import NetworkConfigurer
from cloudinit.net.ifupdown import IfUpDownConfigurer
from cloudinit.net.netplan import NetplanConfigurer
from cloudinit.net.network_manager import NetworkManagerConfigurer

DEFAULT_PRIORITY = [
    IfUpDownConfigurer,
    NetworkManagerConfigurer,
    NetplanConfigurer,
]


def search_configurer(
    priority=None, target=None
) -> List[Type[NetworkConfigurer]]:
    if priority is None:
        priority = DEFAULT_PRIORITY

    unknown = [i for i in priority if i not in DEFAULT_PRIORITY]
    if unknown:
        raise ValueError(
            "Unknown configurers provided in priority list: %s" % unknown)

    found = []
    for configurer in priority:
        if configurer.available(target):
            found.append(configurer)
    return found


def select_configurer(priority=None, target=None) -> Type[NetworkConfigurer]:
    found = search_configurer(priority, target)
    if not found:
        if priority is None:
            priority = DEFAULT_PRIORITY
        tmsg = ""
        if target and target != "/":
            tmsg = " in target=%s" % target
        raise RuntimeError(
            "No available network configurers found%s. Searched "
            "through list: %s" % (tmsg, priority))
    return found[0]
