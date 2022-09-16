# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json
from functools import lru_cache

from requests import exceptions

from cloudinit import dmi
from cloudinit import log as log
from cloudinit import net, netinfo, subp, url_helper, util
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4

# Get LOG
LOG = log.getLogger(__name__)


@lru_cache()
def get_metadata(url, timeout, retries, sec_between, agent, tmp_dir=None):
    # Bring up interface (and try untill one works)
    exception = RuntimeError("Failed to DHCP")

    # Seek iface with DHCP
    for iface in get_interface_list():
        try:
            with EphemeralDHCPv4(
                iface=iface,
                connectivity_url_data={"url": url},
                tmp_dir=tmp_dir,
            ):
                # Check for the metadata route, skip if not there
                if not check_route(url):
                    continue

                # Fetch the metadata
                v1 = read_metadata(url, timeout, retries, sec_between, agent)

                return json.loads(v1)
        except (
            NoDHCPLeaseError,
            subp.ProcessExecutionError,
            RuntimeError,
            exceptions.RequestException,
        ) as exc:
            LOG.error("DHCP Exception: %s", exc)
            exception = exc
    raise exception


# Get interface list, sort, and clean
def get_interface_list():
    ifaces = []
    for iface in net.find_candidate_nics():
        # Skip dummy
        if "dummy" in iface:
            continue
        ifaces.append(iface)

    return ifaces


# Check for /32 route that our dhcp servers inject
# in order to determine if this a customer-run dhcp server
def check_route(url):
    # Get routes, confirm entry exists
    routes = netinfo.route_info()

    # If no tools exist and empty dict is returned
    if "ipv4" not in routes:
        return False

    # Parse each route into a more searchable format
    for route in routes["ipv4"]:
        if route.get("destination", None) in url:
            return True

    return False


# Read the system information from SMBIOS
def get_sysinfo():
    return {
        "manufacturer": dmi.read_dmi_data("system-manufacturer"),
        "subid": dmi.read_dmi_data("system-serial-number"),
    }


# Assumes is Vultr is already checked
def is_baremetal():
    if get_sysinfo()["manufacturer"] != "Vultr":
        return True
    return False


# Confirm is Vultr
def is_vultr():
    # VC2, VDC, and HFC use DMI
    sysinfo = get_sysinfo()

    if sysinfo["manufacturer"] == "Vultr":
        return True

    # Baremetal requires a kernel parameter
    if "vultr" in util.get_cmdline().split():
        return True

    return False


# Read Metadata endpoint
def read_metadata(url, timeout, retries, sec_between, agent):
    url = "%s/v1.json" % url

    # Announce os details so we can handle non Vultr origin
    # images and provide correct vendordata generation.
    headers = {"Metadata-Token": "cloudinit", "User-Agent": agent}

    response = url_helper.readurl(
        url,
        timeout=timeout,
        retries=retries,
        headers=headers,
        sec_between=sec_between,
    )

    if not response.ok():
        raise RuntimeError(
            "Failed to connect to %s: Code: %s" % url, response.code
        )

    return response.contents.decode()


# Wrapped for caching
@lru_cache()
def get_interface_map():
    return net.get_interfaces_by_mac()


# Convert macs to nics
def get_interface_name(mac):
    macs_to_nic = get_interface_map()

    if mac not in macs_to_nic:
        return None

    return macs_to_nic.get(mac)


# Generate network configs
def generate_network_config(interfaces):
    network = {
        "version": 1,
        "config": [
            {
                "type": "nameserver",
                "address": ["108.61.10.10", "2001:19f0:300:1704::6"],
            }
        ],
    }

    # Prepare interface 0, public
    if len(interfaces) > 0:
        public = generate_interface(interfaces[0], primary=True)
        network["config"].append(public)

    # Prepare additional interfaces, private
    for i in range(1, len(interfaces)):
        interface = interfaces[i]

        # Skip interfaces set not to be configured
        if interface.get("unconfigured"):
            continue

        private = generate_interface(interface)
        network["config"].append(private)

    return network


def generate_interface(interface, primary=False):
    interface_name = get_interface_name(interface["mac"])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" % interface["mac"]
        )

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": interface["mac"],
    }

    if primary:
        netcfg["accept-ra"] = 1
        netcfg["subnets"] = [
            {"type": "dhcp", "control": "auto"},
            {"type": "ipv6_slaac", "control": "auto"},
        ]

    if not primary:
        netcfg["subnets"] = [
            {
                "type": "static",
                "control": "auto",
                "address": interface["ipv4"]["address"],
                "netmask": interface["ipv4"]["netmask"],
            }
        ]

    generate_interface_routes(interface, netcfg)
    generate_interface_additional_addresses(interface, netcfg)

    # Add config to template
    return netcfg


def generate_interface_routes(interface, netcfg):
    # Options that may or may not be used
    if "mtu" in interface:
        netcfg["mtu"] = interface["mtu"]

    if "accept-ra" in interface:
        netcfg["accept-ra"] = interface["accept-ra"]

    if "routes" in interface:
        netcfg["subnets"][0]["routes"] = interface["routes"]


def generate_interface_additional_addresses(interface, netcfg):
    # Check for additional IP's
    additional_count = len(interface["ipv4"]["additional"])
    if "ipv4" in interface and additional_count > 0:
        for additional in interface["ipv4"]["additional"]:
            add = {
                "type": "static",
                "control": "auto",
                "address": additional["address"],
                "netmask": additional["netmask"],
            }

            if "routes" in additional:
                add["routes"] = additional["routes"]

            netcfg["subnets"].append(add)

    # Check for additional IPv6's
    additional_count = len(interface["ipv6"]["additional"])
    if "ipv6" in interface and additional_count > 0:
        for additional in interface["ipv6"]["additional"]:
            add = {
                "type": "static6",
                "control": "auto",
                "address": "%s/%s"
                % (additional["network"], additional["prefix"]),
            }

            if "routes" in additional:
                add["routes"] = additional["routes"]

            netcfg["subnets"].append(add)


# Make required adjustments to the network configs provided
def add_interface_names(interfaces):
    for interface in interfaces:
        interface_name = get_interface_name(interface["mac"])
        if not interface_name:
            raise RuntimeError(
                "Interface: %s could not be found on the system"
                % interface["mac"]
            )
        interface["name"] = interface_name

    return interfaces


# vi: ts=4 expandtab
