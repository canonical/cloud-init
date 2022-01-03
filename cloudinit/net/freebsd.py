# This file is part of cloud-init. See LICENSE file for license information.

import cloudinit.net.bsd
from cloudinit import log as logging
from cloudinit import subp, util

LOG = logging.getLogger(__name__)


class Renderer(cloudinit.net.bsd.BSDRenderer):
    def __init__(self, config=None):
        self._route_cpt = 0
        super(Renderer, self).__init__()

    def rename_interface(self, cur_name, device_name):
        self.set_rc_config_value("ifconfig_%s_name" % cur_name, device_name)

    def write_config(self):
        for device_name, v in self.interface_configurations.items():
            net_config = "DHCP"
            if isinstance(v, dict):
                net_config = v.get("address") + " netmask " + v.get("netmask")
                mtu = v.get("mtu")
                if mtu:
                    net_config += " mtu %d" % mtu
            self.set_rc_config_value("ifconfig_" + device_name, net_config)

    def start_services(self, run=False):
        if not run:
            LOG.debug("freebsd generate postcmd disabled")
            return

        for dhcp_interface in self.dhcp_interfaces():
            # Observed on DragonFlyBSD 6. If we use the "restart" parameter,
            # the routes are not recreated.
            subp.subp(
                ["service", "dhclient", "stop", dhcp_interface],
                rcs=[0, 1],
                capture=True,
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
            subp.subp(
                ["service", "dhclient", "start", dhcp_interface],
                rcs=[0, 1],
                capture=True,
            )

    def set_route(self, network, netmask, gateway):
        if network == "0.0.0.0":
            self.set_rc_config_value("defaultrouter", gateway)
        else:
            route_name = "route_net%d" % self._route_cpt
            route_cmd = "-route %s/%s %s" % (network, netmask, gateway)
            self.set_rc_config_value(route_name, route_cmd)
            self._route_cpt += 1


def available(target=None):
    return util.is_FreeBSD() or util.is_DragonFlyBSD()
