#!/usr/bin/env python3
# vi: ts=4 expandtab
#
# Copyright (C) 2021-2022 VMware Inc.
#
# Author: Shreenidhi Shedi <yesshedi@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from collections import OrderedDict
from typing import Optional

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.net import renderer
from cloudinit.net.network_state import NetworkState

LOG = logging.getLogger(__name__)


class CfgParser:
    def __init__(self):
        self.conf_dict = OrderedDict(
            {
                "Match": [],
                "Link": [],
                "Network": [],
                "DHCPv4": [],
                "DHCPv6": [],
                "Address": [],
                "Route": [],
            }
        )

    def update_section(self, sec, key, val):
        for k in self.conf_dict.keys():
            if k == sec:
                self.conf_dict[k].append(key + "=" + str(val))
                # remove duplicates from list
                self.conf_dict[k] = list(dict.fromkeys(self.conf_dict[k]))
                self.conf_dict[k].sort()

    def get_final_conf(self):
        contents = ""
        for k, v in sorted(self.conf_dict.items()):
            if not v:
                continue
            if k == "Address":
                for e in sorted(v):
                    contents += "[" + k + "]\n"
                    contents += e + "\n"
                    contents += "\n"
            else:
                contents += "[" + k + "]\n"
                for e in sorted(v):
                    contents += e + "\n"
                contents += "\n"

        return contents

    def dump_data(self, target_fn):
        if not target_fn:
            LOG.warning("Target file not given")
            return

        contents = self.get_final_conf()
        LOG.debug("Final content: %s", contents)
        util.write_file(target_fn, contents)


class Renderer(renderer.Renderer):
    """
    Renders network information in /etc/systemd/network

    This Renderer is currently experimental and doesn't support all the
    use cases supported by the other renderers yet.
    """

    def __init__(self, config=None):
        if not config:
            config = {}
        self.resolve_conf_fn = config.get(
            "resolve_conf_fn", "/etc/systemd/resolved.conf"
        )
        self.network_conf_dir = config.get(
            "network_conf_dir", "/etc/systemd/network/"
        )

    def generate_match_section(self, iface, cfg: CfgParser):
        sec = "Match"
        match_dict = {
            "name": "Name",
            "driver": "Driver",
            "mac_address": "MACAddress",
        }

        if not iface:
            return

        for k, v in match_dict.items():
            if k in iface and iface[k]:
                cfg.update_section(sec, v, iface[k])

        return iface["name"]

    def generate_link_section(self, iface, cfg: CfgParser):
        sec = "Link"

        if not iface:
            return

        if "mtu" in iface and iface["mtu"]:
            cfg.update_section(sec, "MTUBytes", iface["mtu"])

    def parse_routes(self, conf, cfg: CfgParser):
        sec = "Route"
        route_cfg_map = {
            "gateway": "Gateway",
            "network": "Destination",
            "metric": "Metric",
        }

        # prefix is derived using netmask by network_state
        prefix = ""
        if "prefix" in conf:
            prefix = "/" + str(conf["prefix"])

        for k, v in conf.items():
            if k not in route_cfg_map:
                continue
            if k == "network":
                v += prefix
            cfg.update_section(sec, route_cfg_map[k], v)

    def parse_subnets(self, iface, cfg: CfgParser):
        dhcp = "no"
        sec = "Network"
        for e in iface.get("subnets", []):
            t = e["type"]
            if t == "dhcp4" or t == "dhcp":
                if dhcp == "no":
                    dhcp = "ipv4"
                elif dhcp == "ipv6":
                    dhcp = "yes"
            elif t == "dhcp6":
                if dhcp == "no":
                    dhcp = "ipv6"
                elif dhcp == "ipv4":
                    dhcp = "yes"
            if "routes" in e and e["routes"]:
                for i in e["routes"]:
                    self.parse_routes(i, cfg)
            if "address" in e:
                subnet_cfg_map = {
                    "address": "Address",
                    "gateway": "Gateway",
                    "dns_nameservers": "DNS",
                    "dns_search": "Domains",
                }
                for k, v in e.items():
                    if k == "address":
                        if "prefix" in e:
                            v += "/" + str(e["prefix"])
                        cfg.update_section("Address", subnet_cfg_map[k], v)
                    elif k == "gateway":
                        cfg.update_section("Route", subnet_cfg_map[k], v)
                    elif k == "dns_nameservers" or k == "dns_search":
                        cfg.update_section(sec, subnet_cfg_map[k], " ".join(v))

        cfg.update_section(sec, "DHCP", dhcp)

        if dhcp in ["ipv6", "yes"] and isinstance(
            iface.get("accept-ra", ""), bool
        ):
            cfg.update_section(sec, "IPv6AcceptRA", iface["accept-ra"])

        return dhcp

    # This is to accommodate extra keys present in VMware config
    def dhcp_domain(self, d, cfg: CfgParser):
        for item in ["dhcp4domain", "dhcp6domain"]:
            if item not in d:
                continue
            ret = str(d[item]).casefold()
            try:
                ret = util.translate_bool(ret)
                ret = "yes" if ret else "no"
            except ValueError:
                if ret != "route":
                    LOG.warning("Invalid dhcp4domain value - %s", ret)
                    ret = "no"
            if item == "dhcp4domain":
                section = "DHCPv4"
            else:
                section = "DHCPv6"
            cfg.update_section(section, "UseDomains", ret)

    def parse_dns(self, iface, cfg: CfgParser, ns: NetworkState):
        sec = "Network"

        dns_cfg_map = {
            "search": "Domains",
            "nameservers": "DNS",
            "addresses": "DNS",
        }

        dns = iface.get("dns")
        if not dns and ns.version == 1:
            dns = {
                "search": ns.dns_searchdomains,
                "nameservers": ns.dns_nameservers,
            }
        elif not dns and ns.version == 2:
            return

        for k, v in dns_cfg_map.items():
            if k in dns and dns[k]:
                cfg.update_section(sec, v, " ".join(dns[k]))

    def parse_dhcp_overrides(self, cfg: CfgParser, device, dhcp, version):
        dhcp_config_maps = {
            "UseDNS": "use-dns",
            "UseDomains": "use-domains",
            "UseHostname": "use-hostname",
            "UseNTP": "use-ntp",
        }

        if version == "4":
            dhcp_config_maps.update(
                {
                    "SendHostname": "send-hostname",
                    "Hostname": "hostname",
                    "RouteMetric": "route-metric",
                    "UseMTU": "use-mtu",
                    "UseRoutes": "use-routes",
                }
            )

        if f"dhcp{version}-overrides" in device and dhcp in [
            "yes",
            f"ipv{version}",
        ]:
            dhcp_overrides = device[f"dhcp{version}-overrides"]
            for k, v in dhcp_config_maps.items():
                if v in dhcp_overrides:
                    cfg.update_section(f"DHCPv{version}", k, dhcp_overrides[v])

    def create_network_file(self, link, conf, nwk_dir):
        net_fn_owner = "systemd-network"

        LOG.debug("Setting Networking Config for %s", link)

        net_fn = nwk_dir + "10-cloud-init-" + link + ".network"
        util.write_file(net_fn, conf)
        util.chownbyname(net_fn, net_fn_owner, net_fn_owner)

    def render_network_state(
        self,
        network_state: NetworkState,
        templates: Optional[dict] = None,
        target=None,
    ) -> None:
        network_dir = self.network_conf_dir
        if target:
            network_dir = subp.target_path(target) + network_dir

        util.ensure_dir(network_dir)

        ret_dict = self._render_content(network_state)
        for k, v in ret_dict.items():
            self.create_network_file(k, v, network_dir)

    def _render_content(self, ns: NetworkState) -> dict:
        ret_dict = {}
        for iface in ns.iter_interfaces():
            cfg = CfgParser()

            link = self.generate_match_section(iface, cfg)
            self.generate_link_section(iface, cfg)
            dhcp = self.parse_subnets(iface, cfg)
            self.parse_dns(iface, cfg, ns)

            for route in ns.iter_routes():
                self.parse_routes(route, cfg)

            if ns.version == 2:
                name: Optional[str] = iface["name"]
                # network state doesn't give dhcp domain info
                # using ns.config as a workaround here

                # Check to see if this interface matches against an interface
                # from the network state that specified a set-name directive.
                # If there is a device with a set-name directive and it has
                # set-name value that matches the current name, then update the
                # current name to the device's name. That will be the value in
                # the ns.config['ethernets'] dict below.
                for dev_name, dev_cfg in ns.config["ethernets"].items():
                    if "set-name" in dev_cfg:
                        if dev_cfg.get("set-name") == name:
                            name = dev_name
                            break
                if name in ns.config["ethernets"]:
                    device = ns.config["ethernets"][name]

                    # dhcp{version}domain are extra keys only present in
                    # VMware config
                    self.dhcp_domain(device, cfg)
                    for version in ["4", "6"]:
                        if (
                            f"dhcp{version}domain" in device
                            and "use-domains"
                            in device.get(f"dhcp{version}-overrides", {})
                        ):
                            exception = (
                                f"{name} has both dhcp{version}domain"
                                f" and dhcp{version}-overrides.use-domains"
                                f" configured. Use one"
                            )
                            raise Exception(exception)

                        self.parse_dhcp_overrides(cfg, device, dhcp, version)

            ret_dict.update({link: cfg.get_final_conf()})

        return ret_dict


def available(target=None):
    expected = ["ip", "systemctl"]
    search = ["/usr/sbin", "/bin"]
    for p in expected:
        if not subp.which(p, search=search, target=target):
            return False
    return True


def network_state_to_networkd(ns: NetworkState):
    renderer = Renderer({})
    return renderer._render_content(ns)
