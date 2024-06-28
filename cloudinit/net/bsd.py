# This file is part of cloud-init. See LICENSE file for license information.

import logging
import re
from typing import Optional

from cloudinit import net, subp, util
from cloudinit.distros import bsd_utils
from cloudinit.distros.parsers.resolv_conf import ResolvConf
from cloudinit.net import renderer
from cloudinit.net.network_state import NetworkState

LOG = logging.getLogger(__name__)


class BSDRenderer(renderer.Renderer):
    resolv_conf_fn = "etc/resolv.conf"
    rc_conf_fn = "etc/rc.conf"
    interface_routes = ""
    route_names = ""
    route6_names = ""

    def get_rc_config_value(self, key):
        fn = subp.target_path(self.target, self.rc_conf_fn)
        bsd_utils.get_rc_config_value(key, fn=fn)

    def set_rc_config_value(self, key, value):
        fn = subp.target_path(self.target, self.rc_conf_fn)
        bsd_utils.set_rc_config_value(key, value, fn=fn)

    def __init__(self, config=None):
        if not config:
            config = {}
        self.target = None
        self.interface_configurations = {}
        self.interface_configurations_ipv6 = {}
        self._postcmds = config.get("postcmds", True)

    def _ifconfig_entries(self, settings):
        ifname_by_mac = net.get_interfaces_by_mac()
        for interface in settings.iter_interfaces():
            device_name = interface.get("name")
            device_mac = interface.get("mac_address")
            if device_name and re.match(r"^lo\d+$", device_name):
                continue
            if device_mac not in ifname_by_mac:
                LOG.info("Cannot find any device with MAC %s", device_mac)
            elif device_mac and device_name:
                cur_name = ifname_by_mac[device_mac]
                if cur_name != device_name:
                    LOG.info(
                        "netif service will rename interface %s to %s",
                        cur_name,
                        device_name,
                    )
                    try:
                        self.rename_interface(cur_name, device_name)
                    except NotImplementedError:
                        LOG.error(
                            "Interface renaming is not supported on this OS"
                        )
                        device_name = cur_name

            else:
                device_name = ifname_by_mac[device_mac]

            LOG.info("Configuring interface %s", device_name)

            for subnet in interface.get("subnets", []):
                if subnet.get("type") == "static":
                    if not subnet.get("netmask"):
                        LOG.debug(
                            "Skipping IP %s, because there is no netmask",
                            subnet.get("address"),
                        )
                        continue
                    LOG.debug(
                        "Configuring dev %s with %s / %s",
                        device_name,
                        subnet.get("address"),
                        subnet.get("netmask"),
                    )

                    self.interface_configurations[device_name] = {
                        "address": subnet.get("address"),
                        "netmask": subnet.get("netmask"),
                        "mtu": subnet.get("mtu") or interface.get("mtu"),
                    }

                elif subnet.get("type") == "static6":
                    if not subnet.get("prefix"):
                        LOG.debug(
                            "Skipping IP %s, because there is no prefix",
                            subnet.get("address"),
                        )
                        continue
                    LOG.debug(
                        "Configuring dev %s with %s / %s",
                        device_name,
                        subnet.get("address"),
                        subnet.get("prefix"),
                    )

                    self.interface_configurations_ipv6[device_name] = {
                        "address": subnet.get("address"),
                        "prefix": subnet.get("prefix"),
                        "mtu": subnet.get("mtu") or interface.get("mtu"),
                    }
                elif (
                    subnet.get("type") == "dhcp"
                    or subnet.get("type") == "dhcp4"
                ):
                    self.interface_configurations[device_name] = "DHCP"

    def _route_entries(self, settings):
        routes = list(settings.iter_routes())
        for interface in settings.iter_interfaces():
            subnets = interface.get("subnets", [])
            for subnet in subnets:
                if subnet.get("type") == "static":
                    gateway = subnet.get("gateway")
                    if gateway and len(gateway.split(".")) == 4:
                        routes.append(
                            {
                                "network": "0.0.0.0",
                                "netmask": "0.0.0.0",
                                "gateway": gateway,
                            }
                        )
                elif subnet.get("type") == "static6":
                    gateway = subnet.get("gateway")
                    if gateway and len(gateway.split(":")) > 1:
                        routes.append(
                            {
                                "network": "::",
                                "prefix": "0",
                                "gateway": gateway,
                            }
                        )
                else:
                    continue
                routes += subnet.get("routes", [])

        for route in routes:
            network = route.get("network")
            if not network:
                LOG.debug("Skipping a bad route entry")
                continue
            netmask = (
                route.get("netmask")
                if route.get("netmask")
                else route.get("prefix")
            )
            gateway = route.get("gateway")
            self.set_route(network, netmask, gateway)

    def _resolve_conf(self, settings):
        nameservers = settings.dns_nameservers
        searchdomains = settings.dns_searchdomains
        for interface in settings.iter_interfaces():
            for subnet in interface.get("subnets", []):
                if "dns_nameservers" in subnet:
                    nameservers.extend(subnet["dns_nameservers"])
                if "dns_search" in subnet:
                    searchdomains.extend(subnet["dns_search"])
        # Try to read the /etc/resolv.conf or just start from scratch if that
        # fails.
        try:
            resolvconf = ResolvConf(
                util.load_text_file(
                    subp.target_path(self.target, self.resolv_conf_fn)
                )
            )
            resolvconf.parse()
        except IOError:
            util.logexc(
                LOG,
                "Failed to parse %s, use new empty file",
                subp.target_path(self.target, self.resolv_conf_fn),
            )
            resolvconf = ResolvConf("")
            resolvconf.parse()

        # Add some nameservers
        for server in set(nameservers):
            try:
                resolvconf.add_nameserver(server)
            except ValueError:
                util.logexc(LOG, "Failed to add nameserver %s", server)

        # And add any searchdomains.
        for domain in set(searchdomains):
            try:
                resolvconf.add_search_domain(domain)
            except ValueError:
                util.logexc(LOG, "Failed to add search domain %s", domain)
        util.write_file(
            subp.target_path(self.target, self.resolv_conf_fn),
            str(resolvconf),
            0o644,
        )

    def render_network_state(
        self,
        network_state: NetworkState,
        templates: Optional[dict] = None,
        target=None,
    ) -> None:
        if target:
            self.target = target
        self._ifconfig_entries(settings=network_state)
        self._route_entries(settings=network_state)
        self._resolve_conf(settings=network_state)

        self.write_config()
        self.start_services(run=self._postcmds)

    def dhcp_interfaces(self):
        ic = self.interface_configurations.items
        return [k for k, v in ic() if v == "DHCP"]

    def start_services(self, run=False):
        raise NotImplementedError()

    def write_config(self, target=None):
        raise NotImplementedError()

    def rename_interface(self, cur_name, device_name):
        raise NotImplementedError()

    def set_route(self, network, netmask, gateway):
        raise NotImplementedError()
