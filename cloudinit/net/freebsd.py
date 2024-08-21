# This file is part of cloud-init. See LICENSE file for license information.

import logging

import cloudinit.net.bsd
from cloudinit import distros, net, subp, util

LOG = logging.getLogger(__name__)


class Renderer(cloudinit.net.bsd.BSDRenderer):
    def __init__(self, config=None):
        self._route_cpt = 0
        super(Renderer, self).__init__()

    def rename_interface(self, cur_name, device_name):
        self.set_rc_config_value("ifconfig_%s_name" % cur_name, device_name)

    def write_config(self):
        for device_name, v in self.interface_configurations.items():
            if isinstance(v, dict):
                net_config = "inet %s netmask %s" % (
                    v.get("address"),
                    v.get("netmask"),
                )
                mtu = v.get("mtu")
                if mtu:
                    net_config += " mtu %d" % mtu
            elif v == "DHCP":
                net_config = "DHCP"
            self.set_rc_config_value("ifconfig_" + device_name, net_config)

        for device_name, v in self.interface_configurations_ipv6.items():
            if isinstance(v, dict):
                net_config = "inet6 %s/%d" % (
                    v.get("address"),
                    v.get("prefix"),
                )
                mtu = v.get("mtu")
                if mtu:
                    net_config += " mtu %d" % mtu
            self.set_rc_config_value(
                "ifconfig_%s_ipv6" % device_name, net_config
            )

    def start_services(self, run=False):
        if not run:
            LOG.debug("freebsd generate postcmd disabled")
            return

        for dhcp_interface in self.dhcp_interfaces():
            # Observed on DragonFlyBSD 6. If we use the "restart" parameter,
            # the routes are not recreated.
            net.dhcp.IscDhclient.stop_service(
                dhcp_interface, distros.freebsd.Distro
            )

        subp.subp(["service", "netif", "restart"], capture=True)
        # On FreeBSD 10, the restart of routing and dhclient is likely to fail
        # because
        # - routing: it cannot remove the loopback route, but it will still set
        #   up the default route as expected.
        # - dhclient: it cannot stop the dhclient started by the netif service.
        # In both case, the situation is ok, and we can proceed.
        subp.subp(["service", "routing", "restart"], capture=True, rcs=[0, 1])

        for dhcp_interface in self.dhcp_interfaces():
            net.dhcp.IscDhclient.start_service(
                dhcp_interface, distros.freebsd.Distro
            )

    def set_route(self, network, netmask, gateway):
        if network == "0.0.0.0":
            self.set_rc_config_value("defaultrouter", gateway)
        elif network == "::":
            self.set_rc_config_value("ipv6_defaultrouter", gateway)
        else:
            route_name = f"net{self._route_cpt}"
            if ":" in network:
                route_cmd = f"-net {network}/{netmask} {gateway}"
                self.set_rc_config_value("ipv6_route_" + route_name, route_cmd)
                self.route6_names = f"{self.route6_names} {route_name}"
                self.set_rc_config_value(
                    "ipv6_static_routes", self.route6_names.strip()
                )
            else:
                route_cmd = f"-net {network} -netmask {netmask} {gateway}"
                self.set_rc_config_value("route_" + route_name, route_cmd)
                self.route_names = f"{self.route_names} {route_name}"
                self.set_rc_config_value(
                    "static_routes", self.route_names.strip()
                )
            self._route_cpt += 1


def available(target=None):
    return util.is_FreeBSD() or util.is_DragonFlyBSD()
