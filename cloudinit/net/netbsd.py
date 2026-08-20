# This file is part of cloud-init. See LICENSE file for license information.

import logging
from typing import Optional

import cloudinit.net.bsd
from cloudinit import subp, util

LOG = logging.getLogger(__name__)


class Renderer(cloudinit.net.bsd.BSDRenderer):
    def __init__(self, config: Optional[dict] = None) -> None:
        super(Renderer, self).__init__()

    def write_config(self, target=None) -> None:
        if self.dhcp_interfaces():
            self.set_rc_config_value("dhcpcd", "YES")
            self.set_rc_config_value(
                "dhcpcd_flags", " ".join(self.dhcp_interfaces())
            )
        for device_name, v in self.interface_configurations.items():
            if isinstance(v, dict):
                net_config = v["address"] + " netmask " + v["netmask"]
                mtu = v.get("mtu")
                if mtu:
                    net_config += " mtu %d" % mtu
                self.set_rc_config_value("ifconfig_" + device_name, net_config)

    def start_services(self, run: bool = False) -> None:
        if not run:
            LOG.debug("netbsd generate postcmd disabled")
            return

        subp.subp(["service", "network", "restart"], capture=True)
        if self.dhcp_interfaces():
            subp.subp(["service", "dhcpcd", "restart"], capture=True)

    def set_route(self, network: str, netmask: str, gateway: str) -> None:
        if network == "0.0.0.0":
            self.set_rc_config_value("defaultroute", gateway)


def available(target: Optional[str] = None) -> bool:
    return util.is_NetBSD()
