# This file is part of cloud-init.  See LICENSE file ...

import copy
import io
import logging
import os
import textwrap
from tempfile import SpooledTemporaryFile
from typing import Callable, List, Optional

from cloudinit import features, safeyaml, subp, util
from cloudinit.net import (
    IPV6_DYNAMIC_TYPES,
    SYS_CLASS_NET,
    get_devicelist,
    renderer,
    should_add_gateway_onlink_flag,
    subnet_is_ipv6,
)
from cloudinit.net.network_state import NET_CONFIG_TO_V2, NetworkState

CLOUDINIT_NETPLAN_FILE = "/etc/netplan/50-cloud-init.yaml"

KNOWN_SNAPD_CONFIG = b"""\
# This is the initial network config.
# It can be overwritten by cloud-init or console-conf.
network:
    version: 2
    ethernets:
        all-en:
            match:
                name: "en*"
            dhcp4: true
        all-eth:
            match:
                name: "eth*"
            dhcp4: true
"""

LOG = logging.getLogger(__name__)


def _get_params_dict_by_match(config, match):
    return dict(
        (key, value)
        for (key, value) in config.items()
        if key.startswith(match)
    )


def _extract_addresses(config: dict, entry: dict, ifname, features: Callable):
    """This method parse a cloudinit.net.network_state dictionary (config) and
       maps netstate keys/values into a dictionary (entry) to represent
       netplan yaml. (config v1 -> netplan)

    An example config dictionary might look like:

    {'mac_address': '52:54:00:12:34:00',
     'name': 'interface0',
     'subnets': [
        {'address': '192.168.1.2/24',
         'mtu': 1501,
         'type': 'static'},
        {'address': '2001:4800:78ff:1b:be76:4eff:fe06:1000",
         'mtu': 1480,
         'netmask': 64,
         'type': 'static'}],
      'type: physical',
      'accept-ra': 'true'
    }

    An entry dictionary looks like:

    {'set-name': 'interface0',
     'match': {'macaddress': '52:54:00:12:34:00'},
     'mtu': 1501}

    After modification returns

    {'set-name': 'interface0',
     'match': {'macaddress': '52:54:00:12:34:00'},
     'mtu': 1501,
     'address': ['192.168.1.2/24', '2001:4800:78ff:1b:be76:4eff:fe06:1000"],
     'ipv6-mtu': 1480}

    """

    def _listify(obj, token=" "):
        """
        Helper to convert strings to list of strings, handle single string
        """
        if not obj or not isinstance(obj, str):
            return obj
        if token in obj:
            return obj.split(token)
        else:
            return [
                obj,
            ]

    addresses = []
    routes = []
    nameservers = []
    searchdomains = []
    subnets = config.get("subnets", [])
    if subnets is None:
        subnets = []
    for subnet in subnets:
        sn_type = subnet.get("type")
        if sn_type.startswith("dhcp"):
            if sn_type == "dhcp":
                sn_type += "4"
            entry.update({sn_type: True})
        elif sn_type in IPV6_DYNAMIC_TYPES:
            entry.update({"dhcp6": True})
        elif sn_type in ["static", "static6"]:
            addr = "%s" % subnet.get("address")
            if "prefix" in subnet:
                addr += "/%d" % subnet.get("prefix")
            if subnet.get("gateway"):
                new_route = {
                    "via": subnet.get("gateway"),
                    "to": "default",
                }
                # If the gateway is not contained within the subnet's
                # network, mark it as on-link so that it can still be
                # reached.
                if should_add_gateway_onlink_flag(subnet["gateway"], addr):
                    LOG.debug(
                        "Gateway %s is not contained within subnet %s,"
                        " adding on-link flag",
                        subnet["gateway"],
                        addr,
                    )
                    new_route["on-link"] = True
                routes.append(new_route)
            if "dns_nameservers" in subnet:
                nameservers += _listify(subnet.get("dns_nameservers", []))
            if "dns_search" in subnet:
                searchdomains += _listify(subnet.get("dns_search", []))
            if "mtu" in subnet:
                mtukey = "mtu"
                if subnet_is_ipv6(subnet) and "ipv6-mtu" in features():
                    mtukey = "ipv6-mtu"
                entry.update({mtukey: subnet.get("mtu")})
            for route in subnet.get("routes", []):
                to_net = "%s/%s" % (route.get("network"), route.get("prefix"))
                new_route = {
                    "via": route.get("gateway"),
                    "to": to_net,
                }
                if "metric" in route:
                    new_route.update({"metric": route.get("metric", 100)})
                routes.append(new_route)

            addresses.append(addr)

    if "mtu" in config:
        entry_mtu = entry.get("mtu")
        if entry_mtu and config["mtu"] != entry_mtu:
            LOG.warning(
                "Network config: ignoring %s device-level mtu:%s because"
                " ipv4 subnet-level mtu:%s provided.",
                ifname,
                config["mtu"],
                entry_mtu,
            )
        else:
            entry["mtu"] = config["mtu"]
    if len(addresses) > 0:
        entry.update({"addresses": addresses})
    if len(routes) > 0:
        entry.update({"routes": routes})
    if len(nameservers) > 0:
        ns = {"addresses": nameservers}
        entry.update({"nameservers": ns})
    if len(searchdomains) > 0:
        ns = entry.get("nameservers", {})
        ns.update({"search": searchdomains})
        entry.update({"nameservers": ns})
    if "accept-ra" in config and config["accept-ra"] is not None:
        entry.update({"accept-ra": util.is_true(config.get("accept-ra"))})


def _extract_bond_slaves_by_name(interfaces, entry, bond_master):
    bond_slave_names = sorted(
        [
            name
            for (name, cfg) in interfaces.items()
            if cfg.get("bond-master", None) == bond_master
        ]
    )
    if len(bond_slave_names) > 0:
        entry.update({"interfaces": bond_slave_names})


def _clean_default(target=None):
    # clean out any known default files and derived files in target
    # LP: #1675576
    tpath = subp.target_path(target, "etc/netplan/00-snapd-config.yaml")
    if not os.path.isfile(tpath):
        return
    content = util.load_binary_file(tpath)
    if content != KNOWN_SNAPD_CONFIG:
        return

    derived = [
        subp.target_path(target, f)
        for f in (
            "run/systemd/network/10-netplan-all-en.network",
            "run/systemd/network/10-netplan-all-eth.network",
            "run/systemd/generator/netplan.stamp",
        )
    ]
    existing = [f for f in derived if os.path.isfile(f)]
    LOG.debug(
        "removing known config '%s' and derived existing files: %s",
        tpath,
        existing,
    )

    for f in [tpath] + existing:
        os.unlink(f)


def netplan_api_write_yaml_file(net_config_content: str) -> bool:
    """Use netplan.State._write_yaml_file to write netplan config

    Where netplan python API exists, prefer to use of the private
    _write_yaml_file to ensure proper permissions and file locations
    are chosen by the netplan python bindings in the environment.

    By calling the netplan API, allow netplan versions to change behavior
    related to file permissions and treatment of sensitive configuration
    under the API call to _write_yaml_file.

    In future netplan releases, security-sensitive config may be written to
    separate file or directory paths than world-readable configuration parts.
    """
    try:
        from netplan.parser import Parser  # type: ignore
        from netplan.state import State  # type: ignore
    except ImportError:
        LOG.debug(
            "No netplan python module. Fallback to write %s",
            CLOUDINIT_NETPLAN_FILE,
        )
        return False
    try:
        with SpooledTemporaryFile(mode="w") as f:
            f.write(net_config_content)
            f.flush()
            f.seek(0, io.SEEK_SET)
            parser = Parser()
            parser.load_yaml(f)
            state_output_file = State()
            state_output_file.import_parser_results(parser)

            # Write our desired basename 50-cloud-init.yaml, allow netplan to
            # determine default root-dir /etc/netplan and/or specialized
            # filenames or read permissions based on whether this config
            # contains secrets.
            state_output_file._write_yaml_file(
                os.path.basename(CLOUDINIT_NETPLAN_FILE)
            )
    except Exception as e:
        LOG.warning(
            "Unable to render network config using netplan python module."
            " Fallback to write %s. %s",
            CLOUDINIT_NETPLAN_FILE,
            e,
        )
        return False
    LOG.debug("Rendered netplan config using netplan python API")
    return True


def has_netplan_config_changed(cfg_file: str, content: str) -> bool:
    """Return True when new netplan config has changed vs previous."""
    if not os.path.exists(cfg_file):
        # This is our first write of netplan's cfg_file, representing change.
        return True
    # Check prev cfg vs current cfg. Ignore comments
    prior_cfg = util.load_yaml(util.load_text_file(cfg_file))
    return prior_cfg != util.load_yaml(content)


def fallback_write_netplan_yaml(cfg_file: str, content: str):
    """Write netplan config to cfg_file because python API was unavailable."""
    mode = 0o600 if features.NETPLAN_CONFIG_ROOT_READ_ONLY else 0o644
    if os.path.exists(cfg_file):
        current_mode = util.get_permissions(cfg_file)
        if current_mode & mode == current_mode:
            # preserve mode if existing perms are more strict
            mode = current_mode
    util.write_file(cfg_file, content, mode=mode)


class Renderer(renderer.Renderer):
    """Renders network information in a /etc/netplan/network.yaml format."""

    NETPLAN_GENERATE = ["netplan", "generate"]
    NETPLAN_INFO = ["netplan", "info"]

    def __init__(self, config=None):
        if not config:
            config = {}
        self.netplan_path = config.get("netplan_path", CLOUDINIT_NETPLAN_FILE)
        self.netplan_header = config.get("netplan_header", None)
        self._postcmds = config.get("postcmds", False)
        self.clean_default = config.get("clean_default", True)
        self._features = config.get("features") or []

    def features(self) -> List[str]:
        if not self._features:
            try:
                info_blob, _err = subp.subp(self.NETPLAN_INFO, capture=True)
                info = util.load_yaml(info_blob)
                self._features = info["netplan.io"]["features"]
            except subp.ProcessExecutionError:
                # if the info subcommand is not present then we don't have any
                # new features
                pass
            except (TypeError, KeyError) as e:
                LOG.debug("Failed to list features from netplan info: %s", e)
        return self._features

    def render_network_state(
        self,
        network_state: NetworkState,
        templates: Optional[dict] = None,
        target=None,
    ) -> None:
        # check network state for version
        # if v2, then extract network_state.config
        # else render_v2_from_state
        fpnplan = os.path.join(subp.target_path(target), self.netplan_path)

        util.ensure_dir(os.path.dirname(fpnplan))

        # render from state
        content = self._render_content(network_state)

        # normalize header
        header = self.netplan_header if self.netplan_header else ""
        if not header.endswith("\n"):
            header += "\n"
        content = header + content

        netplan_config_changed = has_netplan_config_changed(fpnplan, content)
        if not netplan_api_write_yaml_file(content):
            fallback_write_netplan_yaml(fpnplan, content)

        if self.clean_default:
            _clean_default(target=target)
        self._netplan_generate(
            run=self._postcmds, config_changed=netplan_config_changed
        )
        self._net_setup_link(run=self._postcmds)

    def _netplan_generate(self, run: bool, config_changed: bool):
        if not run:
            LOG.debug("netplan generate postcmds disabled")
            return
        if not config_changed:
            LOG.debug(
                "skipping call to `netplan generate`."
                " reason: identical netplan config"
            )
            return
        subp.subp(self.NETPLAN_GENERATE, capture=True)

    def _net_setup_link(self, run=False):
        """To ensure device link properties are applied, we poke
        udev to re-evaluate networkd .link files and call
        the setup_link udev builtin command
        """
        if not run:
            LOG.debug("netplan net_setup_link postcmd disabled")
            return
        elif "net.ifnames=0" in util.get_cmdline():
            LOG.debug("Predictable interface names disabled.")
            return
        setup_lnk = ["udevadm", "test-builtin", "net_setup_link"]

        # It's possible we can race a udev rename and attempt to run
        # net_setup_link on a device that no longer exists. When this happens,
        # we don't know what the device was renamed to, so re-gather the
        # entire list of devices and try again.
        last_exception = Exception
        for _ in range(5):
            try:
                for iface in get_devicelist():
                    if os.path.islink(SYS_CLASS_NET + iface):
                        subp.subp(
                            setup_lnk + [SYS_CLASS_NET + iface], capture=True
                        )
                break
            except subp.ProcessExecutionError as e:
                last_exception = e
        else:
            raise RuntimeError(
                "'udevadm test-builtin net_setup_link' unable to run "
                "successfully for all devices."
            ) from last_exception

    def _render_content(self, network_state: NetworkState) -> str:
        # if content already in netplan format, pass it back
        if network_state.version == 2:
            LOG.debug("V2 to V2 passthrough")
            return safeyaml.dumps(
                {"network": network_state.config},
                explicit_start=False,
                explicit_end=False,
            )

        ethernets = {}
        wifis: dict = {}
        bridges = {}
        bonds = {}
        vlans = {}
        content = []

        interfaces = network_state._network_state.get("interfaces", [])

        nameservers = network_state.dns_nameservers
        searchdomains = network_state.dns_searchdomains

        for config in network_state.iter_interfaces():
            ifname = config.get("name")
            # filter None (but not False) entries up front
            ifcfg = dict(filter(lambda it: it[1] is not None, config.items()))

            if_type = ifcfg.get("type")
            if if_type == "physical":
                # required_keys = ['name', 'mac_address']
                eth = {
                    "set-name": ifname,
                    "match": ifcfg.get("match", None),
                }
                if eth["match"] is None:
                    macaddr = ifcfg.get("mac_address", None)
                    if macaddr is not None:
                        eth["match"] = {"macaddress": macaddr.lower()}
                    else:
                        del eth["match"]
                        del eth["set-name"]
                _extract_addresses(ifcfg, eth, ifname, self.features)
                ethernets.update({ifname: eth})

            elif if_type == "bond":
                # required_keys = ['name', 'bond_interfaces']
                bond = {}
                bond_config = {}
                # extract bond params and drop the bond_ prefix as it's
                # redundant in v2 yaml format
                v2_bond_map = NET_CONFIG_TO_V2["bond"]
                for match in ["bond_", "bond-"]:
                    bond_params = _get_params_dict_by_match(ifcfg, match)
                    for param, value in bond_params.items():
                        newname = v2_bond_map.get(param.replace("_", "-"))
                        if newname is None:
                            continue
                        bond_config.update({newname: value})

                if len(bond_config) > 0:
                    bond.update({"parameters": bond_config})
                if ifcfg.get("mac_address"):
                    bond["macaddress"] = ifcfg["mac_address"].lower()
                slave_interfaces = ifcfg.get("bond-slaves")
                if slave_interfaces == "none":
                    _extract_bond_slaves_by_name(interfaces, bond, ifname)
                _extract_addresses(ifcfg, bond, ifname, self.features)
                bonds.update({ifname: bond})

            elif if_type == "bridge":
                # required_keys = ['name', 'bridge_ports']
                #
                # Rather than raise an exception on `sorted(None)`, log a
                # warning and skip this interface when invalid configuration is
                # received.
                bridge_ports = ifcfg.get("bridge_ports")
                if bridge_ports is None:
                    LOG.warning(
                        "Invalid config. The key",
                        f"'bridge_ports' is required in {config}.",
                    )
                    continue
                ports = sorted(copy.copy(bridge_ports))
                bridge: dict = {
                    "interfaces": ports,
                }
                # extract bridge params and drop the bridge prefix as it's
                # redundant in v2 yaml format
                match_prefix = "bridge_"
                params = _get_params_dict_by_match(ifcfg, match_prefix)
                br_config = {}

                # v2 yaml uses different names for the keys
                # and at least one value format change
                v2_bridge_map = NET_CONFIG_TO_V2["bridge"]
                for param, value in params.items():
                    newname = v2_bridge_map.get(param)
                    if newname is None:
                        continue
                    br_config.update({newname: value})
                    if newname in ["path-cost", "port-priority"]:
                        # <interface> <value> -> <interface>: int(<value>)
                        newvalue = {}
                        for val in value:
                            (port, portval) = val.split()
                            newvalue[port] = int(portval)
                        br_config.update({newname: newvalue})

                if len(br_config) > 0:
                    bridge.update({"parameters": br_config})
                if ifcfg.get("mac_address"):
                    bridge["macaddress"] = ifcfg["mac_address"].lower()
                _extract_addresses(ifcfg, bridge, ifname, self.features)
                bridges.update({ifname: bridge})

            elif if_type == "vlan":
                # required_keys = ['name', 'vlan_id', 'vlan-raw-device']
                vlan = {
                    "id": ifcfg.get("vlan_id"),
                    "link": ifcfg.get("vlan-raw-device"),
                }
                macaddr = ifcfg.get("mac_address", None)
                if macaddr is not None:
                    vlan["macaddress"] = macaddr.lower()
                _extract_addresses(ifcfg, vlan, ifname, self.features)
                vlans.update({ifname: vlan})

        # inject global nameserver values under each all interface which
        # has addresses and do not already have a DNS configuration
        if nameservers or searchdomains:
            nscfg = {"addresses": nameservers, "search": searchdomains}
            for section in [ethernets, wifis, bonds, bridges, vlans]:
                for _name, cfg in section.items():
                    if "nameservers" in cfg or "addresses" not in cfg:
                        continue
                    cfg.update({"nameservers": nscfg})

        # workaround yaml dictionary key sorting when dumping
        def _render_section(name, section):
            if section:
                dump = safeyaml.dumps(
                    {name: section},
                    explicit_start=False,
                    explicit_end=False,
                    noalias=True,
                )
                txt = textwrap.indent(dump, " " * 4)
                return [txt]
            return []

        content.append("network:\n    version: 2\n")
        content += _render_section("ethernets", ethernets)
        content += _render_section("wifis", wifis)
        content += _render_section("bonds", bonds)
        content += _render_section("bridges", bridges)
        content += _render_section("vlans", vlans)

        return "".join(content)


def available(target=None):
    expected = ["netplan"]
    search = ["/usr/sbin", "/sbin"]
    for p in expected:
        if not subp.which(p, search=search, target=target):
            return False
    return True
