# This file is part of cloud-init. See LICENSE file for license information.

from typing import List, Tuple, Type

from cloudinit.net import (
    RendererNotFoundError,
    eni,
    freebsd,
    netbsd,
    netplan,
    network_manager,
    networkd,
    openbsd,
    renderer,
    sysconfig,
)

NAME_TO_RENDERER = {
    "eni": eni,
    "freebsd": freebsd,
    "netbsd": netbsd,
    "netplan": netplan,
    "network-manager": network_manager,
    "networkd": networkd,
    "openbsd": openbsd,
    "sysconfig": sysconfig,
}

DEFAULT_PRIORITY = [
    "eni",
    "sysconfig",
    "netplan",
    "network-manager",
    "freebsd",
    "netbsd",
    "openbsd",
    "networkd",
]


def search(
    priority=None, first=False
) -> List[Tuple[str, Type[renderer.Renderer]]]:
    if priority is None:
        priority = DEFAULT_PRIORITY

    available = NAME_TO_RENDERER

    unknown = [i for i in priority if i not in available]
    if unknown:
        raise ValueError(
            "Unknown renderers provided in priority list: %s" % unknown
        )

    found = []
    for name in priority:
        render_mod = available[name]
        if render_mod.available():
            cur = (name, render_mod.Renderer)
            if first:
                return [cur]
            found.append(cur)

    return found


def select(priority=None) -> Tuple[str, Type[renderer.Renderer]]:
    found = search(priority, first=True)
    if not found:
        if priority is None:
            priority = DEFAULT_PRIORITY
        raise RendererNotFoundError(
            "No available network renderers found. Searched through list: %s"
            % priority
        )
    return found[0]
