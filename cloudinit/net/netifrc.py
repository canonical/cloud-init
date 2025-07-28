# Copyright 2025 David Timber
#
# Author: David Timber <dxdt@dev.snart.me>
# Gentoo Netifrc net renderer
#
# This file is part of cloud-init. See LICENSE file for license information.

r"""
List of implemented vars:
  General:
    - config_
    - dhcp_ (release nodns nontp nonis nogateway nosendhost)
    - dhcpcd_ (dhcpv4 only "-4" and dhcpv6 only "-6")
    - routes_
    - dns_search_
    - dns_servers_
    - mtu_
    - mac_

  Bridge support:
    - bridge_
    - bridge_forward_delay_
    - bridge_hello_time_
    - bridge_stp_state_

  Bond support:
    - mode_
    - fail_over_mac_
    - arp_validate_
    - arp_interval_
    - arp_ip_target_
    - downdelay_
    - updelay_
    - lacp_rate_
    - ad_select_
    - xmit_hash_policy_
    - num_grat_arp_
    - miimon_
    - primary_
    - primary_reselect_
    - all_slaves_active_
    - min_links_

  VLAN support:
    - _vlanN_
    - vlans_
    - _vlanN_name

  Wake on LAN support:
    - ethtool_change_

To list all prefixes that appear in the examples, from /netifrc/doc, run:

  grep -hoP '\K(\w+)_(?=[\w_]+=)' *.example.* | sort | uniq

No metric support:
Netifrc only supports per-interface link through metric_. There's no
counterpart config in Netifrc, so subnet metric settings will be ignored. Use
route metric instead.

  routes:
   - to: 0.0.0.0/0
     via: 10.23.2.1
     metric: 3

IPv6 support:

Netifrc can use both dhcpcd and dhclient backends.As dhcpcd is "Gentoo's long
time default" according to the handbook, the module will assume dhcpcd.
The kernel's accept_ra implementation has a range of issues on modern systems
such as Gentoo. The module WOULD NOT use sysctl to set kernel's accept_ra and
expect that the DHCP client backend will do router solicitation and processing
of RA messages. Currently, it is not possible to implement accept-ra option as
neither dhcpcd or dhclient does not offer an option to disable SLAAC.
dhcp[46]-overrides:

https://cloudinit.readthedocs.io/en/latest/reference/network-config-format-v2.html#dhcp4-overrides-and-dhcp6-overrides-mapping
https://wiki.gentoo.org/wiki/Handbook:X86/Networking/Modular/en#DHCP

NOTE: they're currently not defined in the schema!

These options are originally intended for Netplan, but the Netifrc module
honours them when passed. However, the module expects them to be an array, not
a mapping. Currently, it is not possible to specify separate DHCP overrides
for DHCPv4 and DHCPv6. This is a bug in Netifrc dhcpcd module.
Example:
  dhcp4-overrides:
    - release
    - nodns
    - nontp
    - nonis
  dhcp6-overrides:
    - nogateway
    - nosendhost
will be rendered as
`dhcp_IFACE="release nodns nontp nonis nogateway nosendhost"`
DHCPv4 or DHCPv6 only:
It is possible to disable IPv4 or IPv6 like so:
  dhcp4: true
  dhcp6: false
will be rendered as `dhcpcd_IFACE="-4"` to disable IPv6 configuration.
"""

import copy
import logging
import os
from typing import Optional

from cloudinit import subp, util
from cloudinit.net import ipv4_mask_to_net_prefix, renderer
from cloudinit.net.network_state import NetworkState

LOG = logging.getLogger(__name__)


def _str_list(lst):
    return [str(s) for s in lst]


def _iface_var(name):
    r"""
    https://gitweb.gentoo.org/proj/netifrc.git/tree/doc/net.example.Linux.in#n701

    #config_eth0.1="dhcp" - does not work
    #config_eth0_1="dhcp" - does work

    https://gitweb.gentoo.org/proj/netifrc.git/tree/doc/net.example.Linux.in#n670

    #vlan1_name="vlan1"
    #eth0_vlan2_name="eth0.2"
    #eth1_vlan2_name="eth1.2"
    """
    return name.replace(".", "_")


class Renderer(renderer.Renderer):
    """Renders network information in a /etc/conf.d/net format."""

    _bond_opts = {
        "bond_mode": '''mode_%s="%s"''',
        "bond_xmit_hash_policy": '''xmit_hash_policy_%s="%s"''',
        "bond_miimon": '''miimon_%s="%s"''',
        "bond_min_links": '''min_links_%s="%s"''',
        "bond_arp_interval": '''arp_interval_%s="%s"''',
        "bond_arp_ip_target": '''arp_ip_target_%s="%s"''',
        "bond_arp_validate": '''arp_validate_%s="%s"''',
        "bond_ad_select": '''ad_select_%s="%s"''',
        "bond_num_grat_arp": '''num_grat_arp_%s="%s"''',
        "bond_downdelay": '''downdelay_%s="%s"''',
        "bond_updelay": '''updelay_%s="%s"''',
        "bond_lacp_rate": '''lacp_rate_%s="%s"''',
        "bond_fail_over_mac": '''fail_over_mac_%s="%s"''',
        "bond_primary": '''primary_%s="%s"''',
        "bond_primary_reselect": '''primary_reselect_%s="%s"''',
        "bond_all_slaves_active": '''all_slaves_active_%s="%s"''',
        # missing from schema: active_slave, queue_id, num_unsol_na,
        # use_carrier, resend_igmp
    }

    def __init__(self, config=None):
        if not config:
            config = {}
        self.netifrc_header = config.get("netifrc_header", "")
        self.netifrc_path = config.get("netifrc_path", "etc/conf.d/net")
        self.initd_net_prefix = config.get(
            "initd_net_prefix", "etc/init.d/net."
        )
        self.initd_netlo_path = config.get(
            "initd_netlo_path", self.initd_net_prefix + "lo"
        )
        self.resolv_conf_path = config.get(
            "resolv_conf_path", "etc/resolv.conf.head"
        )

    def _render_routes(self, name, routes, lines):
        out = []
        for r in routes:
            if "prefix" in r:
                pl = r["prefix"]
                pfx = "/%d" % (pl,)
            elif "netmask" in r:
                pl = ipv4_mask_to_net_prefix(r["netmask"])
                pfx = "/%d" % (pl,)
            else:
                pl = 0
                pfx = ""

            if "network" not in r or (
                pl == 0 and r["network"] in ["0.0.0.0", "::"]
            ):
                dst = "default"
            else:
                dst = """%s%s""" % (r["network"], pfx)

            if "metric" in r:
                metric = "metric " + str(r["metric"]) + " "
            else:
                metric = ""

            # "gateway" = next hop
            out.append("""%s %svia %s""" % (dst, metric, r["gateway"]))

        lines.append(
            '''routes_%s="\n%s"''' % (_iface_var(name), "\n".join(out))
        )

    def _render_iface(self, name, iface, lines):
        routes = []
        dns_ns = []
        dns_search = []
        subnet_config = []
        dhcp4_opts = []
        dhcp6_opts = []

        accept_ra = iface.get("accept-ra")
        ethernet_wol = iface.get("wakeonlan")
        mtu = iface.get("mtu")
        mac = iface.get("mac_address")

        dhcpv4 = False
        dhcpv6 = False

        for subnet in iface.get("subnets", []):
            stype = subnet["type"]
            addr = subnet.get("address")
            gw = subnet.get("gateway")

            if subnet.get("metric"):
                # no per-subnet metric support in Netifrc
                LOG.warning(
                    "Network config: %s: subnet level metric not supported",
                    name,
                )

            dhcp4_opts += subnet.get("dhcp4-overrides", [])
            dhcp6_opts += subnet.get("dhcp6-overrides", [])
            dns_ns += subnet.get("dns_nameservers", [])
            dns_search += subnet.get("dns_search", [])

            if stype == "dhcp":
                dhcpv4 = dhcpv6 = True
            elif stype == "dhcp4":
                dhcpv4 = True
            elif stype == "dhcp6":
                # "Configure this interface with IPv6 dhcp."
                dhcpv6 = True

            # v1 compat
            # These are not possible with the current Netifrc w/ dhcpcd
            # backend.

            elif stype == "ipv6_dhcpv6-stateful":
                # "Configure this interface with dhcp6."
                # so, no SLAAC? (ipv6ra_noautoconf)
                dhcpv6 = True
            elif stype == "ipv6_dhcpv6-stateless":
                # "Configure this interface with SLAAC and DHCP."
                # same as "dhcp6"
                dhcpv6 = True
            elif stype == "ipv6_slaac":
                # "Configure this interface with dhcp6."
                # (nodhcp6)
                dhcpv6 = True

            elif addr:
                prefix = subnet.get("prefix")
                if prefix:
                    subnet_config.append("%s/%d" % (addr, prefix))
                else:
                    nm = subnet.get("netmask")
                    subnet_config.append("%s netmask %s" % (addr, nm))

            if gw:
                routes.append({"gateway": gw})

            routes += subnet.get("routes", [])

        # config_IFACE="..."

        if dhcpv4 or dhcpv6:
            subnet_config.append("dhcp")
        if not subnet_config:
            subnet_config.append("null")
        lines.append(
            '''config_%s="%s"''' % (_iface_var(name), "\n".join(subnet_config))
        )

        # dhcp(v6)?_IFACE="..."

        if accept_ra is not None:  # no support
            # this is `ipv6ra_noautoconf`. Again, can't do this w/
            # Netifrc+dhcpdc.
            LOG.warning("Network config: %s accept-ra: not supported", name)

        # dhcpv6_ is a dhclient module dialect. As this module assumes dhcpcd,
        # the lists are eventually combined here. Split them up when
        # implementing dhclient in the future.
        #
        # This could cause some issues. If it really did, sadly, Netifrc is not
        # for you.
        dhcp_opts = dhcp4_opts + dhcp6_opts
        if dhcp_opts:
            dhcp_opts = _str_list(dhcp_opts)
            lines.append(
                '''dhcp_%s="%s"''' % (_iface_var(name), " ".join(dhcp_opts))
            )

        if dhcpv4 ^ dhcpv6:
            if dhcpv4:
                lines.append('''dhcpcd_%s="-4"''' % (_iface_var(name),))
            else:
                lines.append('''dhcpcd_%s="-6"''' % (_iface_var(name),))

        # routes_IFACE="..."
        if routes:
            self._render_routes(name, routes, lines)

        if dns_ns:
            lines.append(
                '''dns_servers_%s="%s"'''
                % (_iface_var(name), " ".join(dns_ns))
            )
        if dns_search:
            lines.append(
                '''dns_search_%s="%s"'''
                % (_iface_var(name), " ".join(dns_search))
            )

        if mtu:
            lines.append('''mtu_%s="%s"''' % (_iface_var(name), mtu))

        if mac:
            lines.append('''mac_%s="%s"''' % (_iface_var(name), mac))

        # FIXME: metric_*="..." ?

        if ethernet_wol:
            lines.append('''ethtool_change_%s="wol g"''' % (_iface_var(name),))

    def _emit_bond_params(self, iface, name, lines):
        for k, v in iface.items():
            k = k.replace("-", "_")  # what a mess
            if not k.startswith("bond_"):
                continue
            fmt = self._bond_opts.get(k)
            if fmt is None:
                continue

            if v is list:
                v = " ".join([str(e) for e in v])
            elif v is bool:
                v = str(int(v))
            else:
                v = str(v)

            lines.append(fmt % (_iface_var(name), v))

    def _render_interfaces(self, network_state):
        lines = []
        all_bridged_ports = []
        bond_map = dict[str, set]()
        vlan_map = dict[str, list]()

        for iface in network_state.iter_interfaces():
            name = iface["name"]
            type = iface.get("type")
            bond_master = iface.get("bond-master")

            # `config_lo="..."` is completely valid and works
            # if name == "lo":
            # continue

            iface = copy.deepcopy(iface)

            if bond_master:
                ports = bond_map.setdefault(bond_master, set())
                ports.add(name)

            if type == "vlan":
                link = iface["vlan-raw-device"]
                vlan_id = iface["vlan_id"]
                vlan_list = vlan_map.setdefault(link, [])
                vlan_list.append(str(vlan_id))
                lines.append('''%s_vlan%d_name="%s"''' % (link, vlan_id, name))
            elif type == "bridge":
                # params

                bridge_fd = iface.get("bridge_fd")
                if bridge_fd:
                    lines.append(
                        '''bridge_forward_delay_%s="%d"'''
                        % (_iface_var(name), bridge_fd)
                    )
                bridge_stp = iface.get("bridge_stp")
                if bridge_stp:
                    lines.append(
                        '''bridge_stp_state_%s="%d"'''
                        % (_iface_var(name), bridge_stp)
                    )
                bridge_hello = iface.get("bridge_hello")
                if bridge_hello:
                    lines.append(
                        '''bridge_hello_time_%s="%d"'''
                        % (_iface_var(name), bridge_hello)
                    )

                bridge_ports = iface["bridge_ports"]
                all_bridged_ports += bridge_ports
                lines.append(
                    '''bridge_%s="%s"'''
                    % (_iface_var(name), " ".join(bridge_ports))
                )
            elif type == "bond":
                self._emit_bond_params(iface, name, lines)

            if bond_master and iface.pop("subnets", None):
                # if it's a bond slave but had subnets
                LOG.warning(
                    "Network config: %s: subnets in bond slave removed", name
                )

            iface.pop(
                "name", None
            )  # make sure it's not referenced in the tail
            self._render_iface(name, iface, lines)
            lines.append("")
        lines.append("")

        if all_bridged_ports:
            # "nullify" all_bridged_ports
            # (Netifrc requires slave interfaces to be "null")
            for name in all_bridged_ports:
                lines.append('''config_%s="null"''' % (_iface_var(name),))
            lines.append("")

        if bond_map:
            # construct slaves_*="..."
            for name, ports in bond_map.items():
                lines.append(
                    '''slaves_%s="%s"''' % (_iface_var(name), " ".join(ports))
                )
            lines.append("")

        if vlan_map:
            # construct vlans_*="..."
            for name, vlan_list in vlan_map.items():
                lines.append(
                    '''vlans_%s="%s"'''
                    % (_iface_var(name), " ".join(vlan_list))
                )
            # lines.append("")

        return self.netifrc_header + "\n".join(lines)

    def _render_global_dns(
        self,
        network_state: NetworkState,
    ):
        # OpenRC says: keep it old fashioned and simple
        # Render global DNS in resolv.conf

        resolv = ["# Generated by cloud-init netifrc module"]
        if network_state.dns_nameservers:
            for ns in network_state.dns_nameservers:
                resolv.append("nameserver " + ns)
        if network_state.dns_searchdomains:
            for s in network_state.dns_searchdomains:
                resolv.append("search " + s)

        return self.netifrc_header + "\n".join(resolv)

    def render_network_state(
        self,
        network_state: NetworkState,
        templates: Optional[dict] = None,
        target=None,
    ) -> None:
        fp = subp.target_path(target, self.netifrc_path)
        util.ensure_dir(os.path.dirname(fp))
        util.write_file(fp, self._render_interfaces(network_state))

        # create symlinks
        # TODO: unit test

        for iface in network_state.iter_interfaces():
            name = iface["name"]
            if name == "lo":
                # don't link the original script to itself
                continue
            src = subp.target_path(target, self.initd_netlo_path)
            dst = subp.target_path(target, self.initd_net_prefix + name)
            util.sym_link(src, dst, True)

        # resolv.conf
        # TODO: unit test

        fp = subp.target_path(target, self.resolv_conf_path)
        util.write_file(fp, self._render_global_dns(network_state))


def available(target=None):
    rc = subp.target_path(target, "etc/init.d/net.lo")
    if not os.path.isfile(rc):
        return False

    return True
