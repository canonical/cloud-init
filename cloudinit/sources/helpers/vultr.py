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
    raw = metadata['vendor-data']['config']
    metadata['vendor-data']['config'] = json.loads(raw)

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
    if "vultr" in util.get_cmdline().split():
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

    # Prepare interface 0, public
    if len(md) > 0:
        network['config'].append(generate_public_network_interface(md))

    # Prepare interface 1, private
    if len(md) > 1:
        network['config'].append(generate_private_network_interface(md))

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
    config_template = copy.deepcopy(md['vendor-data']['config'])

    # Add generated network parts
    config_template['network'] = generate_network_config(md['interfaces'])

    return config_template


# This is for the vendor and startup scripts
def generate_user_scripts(md, vendor_config):
    user_scripts = []

    # Raid 1 script
    if md['vendor-data']['raid1-script']:
        user_scripts.append(md['vendor-data']['raid1-script'])

    # Enable multi-queue on linux
    if util.is_Linux() and md['vendor-data']['ethtool-script']:
        ethtool_script = md['vendor-data']['ethtool-script']

        # Tool location
        tool = "/opt/vultr/ethtool"

        # Go through the interfaces
        for netcfg in vendor_config['network']['config']:
            # If the interface has a mac and is physical
            if "mac_address" in netcfg and netcfg['type'] == "physical":
                # Set its multi-queue to num of cores as per RHEL Docs
                name = netcfg['name']
                command = "%s -L %s combined $(nproc --all)" % (tool, name)
                ethtool_script = '%s\n%s' % (ethtool_script, command)

        user_scripts.append(ethtool_script)

    # This is for vendor scripts
    if md['vendor-data']['vendor-script']:
        user_scripts.append(md['vendor-data']['vendor-script'])

    # Startup script
    script = md['startup-script']
    if script and script != "echo No configured startup script":
        user_scripts.append(script)

    return user_scripts


# vi: ts=4 expandtab
