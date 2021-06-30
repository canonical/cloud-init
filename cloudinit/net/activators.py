# This file is part of cloud-init. See LICENSE file for license information.

# This file is mostly copied and pasted from renderers.py. An abstract
# version to encompass both seems overkill at this point
from typing import List, Type

from cloudinit.net.activator import NetworkActivator
from cloudinit.net.ifupdown import IfUpDownActivator
from cloudinit.net.netplan import NetplanActivator
from cloudinit.net.network_manager import NetworkManagerActivator

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

    found = []
    for activator in priority:
        if activator.available(target):
            found.append(activator)
    return found


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
