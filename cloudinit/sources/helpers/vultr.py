# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json
import copy

from cloudinit import log as log
from cloudinit import url_helper
from cloudinit import dmi
from cloudinit import util
from cloudinit import net
from cloudinit.net.dhcp import EphemeralDHCPv4, NoDHCPLeaseError
from functools import lru_cache

# Get LOG
LOG = log.getLogger(__name__)


@lru_cache()
def get_metadata(url, timeout, retries, sec_between):
    # Bring up interface
    try:
        with EphemeralDHCPv4(connectivity_url=url):
            # Fetch the metadata
            v1 = read_metadata(url, timeout, retries, sec_between)
    except (NoDHCPLeaseError) as exc:
        LOG.error("Bailing, DHCP Exception: %s", exc)
        raise

    v1_json = json.loads(v1)
    metadata = v1_json

    # This comes through as a string but is JSON, make a dict
    metadata['vendor-config'] = json.loads(metadata['vendor-config'])

    return metadata


# Read the system information from SMBIOS
def get_sysinfo():
    return {
        'manufacturer': dmi.read_dmi_data("system-manufacturer"),
        'subid': dmi.read_dmi_data("system-serial-number")
    }


# Assumes is Vultr is already checked
def is_baremetal():
    if get_sysinfo()['manufacturer'] != "Vultr":
        return True
    return False


# Confirm is Vultr
def is_vultr():
    # VC2, VDC, and HFC use DMI
    sysinfo = get_sysinfo()

    if sysinfo['manufacturer'] == "Vultr":
        return True

    # Baremetal requires a kernel parameter
    if "vultr" in util.get_cmdline():
        return True

    return False


# Read Metadata endpoint
def read_metadata(url, timeout, retries, sec_between):
    url = "%s/v1.json" % url
    response = url_helper.readurl(url,
                                  timeout=timeout,
                                  retries=retries,
                                  headers={'Metadata-Token': 'vultr'},
                                  sec_between=sec_between)

    if not response.ok():
        raise RuntimeError("Failed to connect to %s: Code: %s" %
                           url, response.code)

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
def generate_network_config(md):
    network = {
        "version": 1,
        "config": [
            {
                "type": "nameserver",
                "address": [
                    "108.61.10.10"
                ]
            }
        ]
    }

    intf = md['interfaces']

    # Prepare interface 0, public
    if len(intf) > 0:
        network['config'].append(generate_public_network_interface(intf))

    # Prepare interface 1, private
    if len(intf) > 1:
        network['config'].append(generate_private_network_interface(intf))

    return network


# Input Metadata and generate public network config part
def generate_public_network_interface(interfaces):
    interface_name = get_interface_name(interfaces[0]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" %
            interfaces[0]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": interfaces[0]['mac'],
        "accept-ra": 1,
        "subnets": [
            {
                "type": "dhcp",
                "control": "auto"
            },
            {
                "type": "dhcp6",
                "control": "auto"
            },
        ]
    }

    # Check for additional IP's
    additional_count = len(interfaces[0]['ipv4']['additional'])
    if "ipv4" in interfaces[0] and additional_count > 0:
        for additional in interfaces[0]['ipv4']['additional']:
            add = {
                "type": "static",
                "control": "auto",
                "address": additional['address'],
                "netmask": additional['netmask']
            }
            netcfg['subnets'].append(add)

    # Check for additional IPv6's
    additional_count = len(interfaces[0]['ipv6']['additional'])
    if "ipv6" in interfaces[0] and additional_count > 0:
        for additional in interfaces[0]['ipv6']['additional']:
            add = {
                "type": "static6",
                "control": "auto",
                "address": additional['address'],
                "netmask": additional['netmask']
            }
            netcfg['subnets'].append(add)

    # Add config to template
    return netcfg


# Input Metadata and generate private network config part
def generate_private_network_interface(interfaces):
    interface_name = get_interface_name(interfaces[1]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" %
            interfaces[1]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": interfaces[1]['mac'],
        "accept-ra": 1,
        "subnets": [
            {
                "type": "static",
                "control": "auto",
                "address": interfaces[1]['ipv4']['address'],
                "netmask": interfaces[1]['ipv4']['netmask']
            }
        ]
    }

    return netcfg


# Generate the vendor config
# This configuration is to replicate how
# images are deployed on Vultr before Cloud-Init
def generate_config(md):
    # Create vendor config
    config_template = copy.deepcopy(md['vendor-config'])

    # Add generated network parts
    config_template['network'] = generate_network_config(md)

    # Linux specific packages
    if util.is_Linux():
        config_template['packages'].append("ethtool")

    return config_template


# This is for the vendor and startup scripts
def generate_user_scripts(script, vendor_config):
    # Define vendor script
    vendor_script = "#!/bin/bash"

    # Go through the interfaces
    for netcfg in vendor_config['network']['config']:
        # If the interface has a mac and is physical
        if "mac_address" in netcfg and netcfg['type'] == "physical":
            # Enable multi-queue on linux
            # This is executed as a vendor script
            if util.is_Linux():
                # Set its multi-queue to num of cores as per RHEL Docs
                name = netcfg['name']
                command = "ethtool -L %s combined $(nproc --all)" % name
                vendor_script = '%s\n%s' % (vendor_script, command)

    vendor_script = '%s\n' % vendor_script

    # Vendor script and start the array
    user_scripts = [vendor_script]

    # Startup script
    if script and script != "echo No configured startup script":
        user_scripts.append("%s\n" % script)

    return user_scripts


# vi: ts=4 expandtab
