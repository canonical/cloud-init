# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import copy
import base64

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
def get_metadata(params):
    params = json.loads(params)

    # Bring up interface
    try:
        with EphemeralDHCPv4(connectivity_url=params['url']):
            # Fetch the metadata
            v1 = fetch_metadata(params)
    except (NoDHCPLeaseError) as exc:
        LOG.error("DHCP failed, cannot continue. Exception: %s",
                  exc)
        raise

    v1_json = json.loads(v1)
    metadata = v1_json

    # This comes through as a string but is JSON, make a dict
    metadata['vendor-config'] = json.loads(metadata['vendor-config'])

    return json.dumps(metadata)


def get_cached_metadata(args):
    return json.loads(get_metadata(json.dumps(args)))


# Read the system information from SMBIOS
def get_sysinfo():
    return {
        'manufacturer': dmi.read_dmi_data("system-manufacturer"),
        'subid': dmi.read_dmi_data("system-serial-number"),
        'product': dmi.read_dmi_data("system-product-name"),
        'family': dmi.read_dmi_data("system-family")
    }


# Confirm is Vultr
def is_vultr():
    # VC2, VDC, and HFC use DMI
    sysinfo = get_sysinfo()

    if sysinfo['manufacturer'] == "Vultr":
        return True

    # Baremetal requires a kernel parameter
    if "vultr" in util.get_cmdline():
        return True

    # An extra fallback if the others fail
    # This needs to be a directory
    if os.path.exists("/etc/vultr") and os.path.isdir("/etc/vultr"):
        return True

    return False


def convert_to_base64(string):
    string_bytes = string.encode('ascii')
    b64_bytes = base64.b64encode(string_bytes)
    return b64_bytes.decode('ascii')


# Read Metadata endpoint
def read_metadata(params):
    response = url_helper.readurl(params['url'],
                                  timeout=params['timeout'],
                                  retries=params['retries'],
                                  headers={'Metadata-Token': 'vultr'},
                                  sec_between=params['wait'])

    if not response.ok():
        raise RuntimeError("Failed to connect to %s: Code: %s" %
                           params['url'], response.code)

    return response.contents.decode()


# Get Metadata by flag
def fetch_metadata(params):
    req = dict(params)
    req['url'] = "%s/v1.json" % params['url']

    return read_metadata(req)


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
def generate_network_config(config):
    md = get_cached_metadata(config)

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
    if len(md['interfaces']) > 0:
        network['config'].append(generate_public_network_interface(md))

    # Prepare interface 1, private
    if len(md['interfaces']) > 1:
        network['config'].append(generate_private_network_interface(md))

    return network


# Input Metadata and generate public network config part
def generate_public_network_interface(md):
    interface_name = get_interface_name(md['interfaces'][0]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" %
            md['interfaces'][0]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": md['interfaces'][0]['mac'],
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
    additional_count = len(md['interfaces'][0]['ipv4']['additional'])
    if "ipv4" in md['interfaces'][0] and additional_count > 0:
        for additional in md['interfaces'][0]['ipv4']['additional']:
            add = {
                "type": "static",
                "control": "auto",
                "address": additional['address'],
                "netmask": additional['netmask']
            }
            netcfg['subnets'].append(add)

    # Check for additional IPv6's
    additional_count = len(md['interfaces'][0]['ipv6']['additional'])
    if "ipv6" in md['interfaces'][0] and additional_count > 0:
        for additional in md['interfaces'][0]['ipv6']['additional']:
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
def generate_private_network_interface(md):
    interface_name = get_interface_name(md['interfaces'][1]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" %
            md['interfaces'][1]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": md['interfaces'][1]['mac'],
        "accept-ra": 1,
        "subnets": [
            {
                "type": "static",
                "control": "auto",
                "address": md['interfaces'][1]['ipv4']['address'],
                "netmask": md['interfaces'][1]['ipv4']['netmask']
            }
        ]
    }

    return netcfg


# Generate the vendor config
# This configuration is to replicate how
# images are deployed on Vultr before Cloud-Init
def generate_config(config):
    LOG.debug("DS: %s", json.dumps(config))
    md = get_cached_metadata(config)

    # Grab the startup script
    script = md['startup-script']

    # Create vendor config
    config_template = copy.deepcopy(md['vendor-config'])

    # Add generated network parts
    config_template['network'] = generate_network_config(config)

    # Linux specific packages
    if util.is_Linux():
        config_template['packages'].append("ethtool")

    # Define vendor script
    vendor_script = "#!/bin/bash"

    # Go through the interfaces
    for netcfg in config_template['network']['config']:
        # If the interface has a mac and is physical
        if "mac_address" in netcfg and netcfg['type'] == "physical":
            # Enable multi-queue on linux
            # This is executed as a vendor script
            if util.is_Linux():
                # Set its multi-queue to num of cores as per RHEL Docs
                name = netcfg['name']
                command = "ethtool -L %s combined $(nproc --all)" % name
                vendor_script = '%s\n%s' % (vendor_script, command)

    # Add write_files if it is not present in the template
    if 'write_files' not in config_template.keys():
        config_template['write_files'] = []

    # Add vendor script to config
    config_template['write_files'].append(
        {
            'encoding': 'b64',
            'content': convert_to_base64(vendor_script),
            'owner': 'root:root',
            'path': '/var/lib/scripts/vendor/vultr-interface-setup.sh',
            'permissions': '0750'
        }
    )

    # Write the startup script
    if script and script != "echo No configured startup script":
        config_template['write_files'].append(
            {
                'encoding': 'b64',
                'content': convert_to_base64(script),
                'owner': 'root:root',
                'path': '/var/lib/scripts/vendor/vultr-user-startup.sh',
                'permissions': '0750'
            }
        )

    return config_template


# vi: ts=4 expandtab
