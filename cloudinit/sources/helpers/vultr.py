# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import copy
import re
import ipaddress

from cloudinit import log as log
from cloudinit import url_helper
from cloudinit import dmi
from cloudinit import util
from cloudinit import net
from cloudinit import subp

# Get logger
LOGGER = log.getLogger(__name__)

# Dict of all API Endpoints
API_MAP = {
    "vendor-config": "/latest/meta-data/vendor-config",
    "v1.json": "/v1.json",
    "startup-script": "/latest/startup-script",
    "user-data": "/latest/user-data",
    "ssh-keys": "/current/ssh-keys"
}


# Cache
MAC_TO_NICS = None
METADATA = None


# Cache the metadata for optimization
def get_metadata(params):
    global METADATA

    if not METADATA:
        vendor = fetch_metadata("vendor-config", params)
        vendor_object = json.loads(vendor)

        v1 = fetch_metadata("v1.json", params)
        v1_json = json.loads(v1)

        METADATA = {
            'vendor-config': vendor_object,
            'v1': v1_json,
            'startup-script': fetch_metadata("startup-script", params),
            'user-data': fetch_metadata("user-data", params),
            'ssh-keys': fetch_metadata("ssh-keys", params),
        }

    return METADATA


# Read the system information from SMBIOS
def get_sysinfo():
    return {
        'manufacturer': dmi.read_dmi_data("system-manufacturer"),
        'subid': dmi.read_dmi_data("system-serial-number"),
        'product': dmi.read_dmi_data("system-product-name"),
        'family': dmi.read_dmi_data("system-family")
    }


# Get kernel parameters
def get_kernel_parameters():
    if not os.path.exists("/proc/cmdline"):
        return ""

    file = open("/proc/cmdline")
    content = file.read()
    file.close()

    if "root=" not in content:
        return ""

    return re.sub(r'.+root=', '', content)[1].strip()


# Confirm is Vultr
def is_vultr():
    # VC2, VDC, and HFC use DMI
    sysinfo = get_sysinfo()

    if sysinfo['manufacturer'] == "Vultr":
        return True

    # Baremetal requires a kernel parameter
    if "vultr" in get_kernel_parameters():
        return True

    # An extra fallback if the others fail
    # This needs to be a directory
    if os.path.exists("/etc/vultr") and os.path.isdir("/etc/vultr"):
        return True

    return False


# Write vendor startup script
def write_vendor_script(fname, content):
    os.makedirs("/var/lib/scripts/vendor/", exist_ok=True)
    file = open("/var/lib/scripts/vendor/%s" % fname, "w")
    file.write("#!/bin/bash")
    for line in content:
        file.write(line)
    file.close()
    command = ["chmod", "+x", "/var/lib/scripts/vendor/%s" % fname]

    try:
        subp.subp(command)
    except Exception as err:
        raise RuntimeError(
            "Command: %s failed to execute. Error: %s" %
            (" ".join(command), err))


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


# Translate flag to endpoint
def get_url(url, flag):
    if flag in API_MAP:
        return url + API_MAP[flag]
    return ""


# Get Metadata by flag
def fetch_metadata(flag, params):
    req = dict(params)
    req['url'] = get_url(params['url'], flag)

    if req['url'] == "":
        raise RuntimeError("Not a valid endpoint. Flag: %s" % flag)

    return read_metadata(req)


# Convert macs to nics
def get_interface_name(mac):
    global MAC_TO_NICS

    # Define it if empty
    if not MAC_TO_NICS:
        MAC_TO_NICS = net.get_interfaces_by_mac()

    if mac not in MAC_TO_NICS:
        return None

    return MAC_TO_NICS.get(mac)


# Convert a netmask to cidr
def to_cidr(mask):
    ip = ipaddress.IPv4Network((0, mask))
    return str(ip.prefixlen)


# Cloud-init does not support turning on any interface beyond
# the first.
def bringup_nic(nic, config):
    return True

    md = get_metadata(config)

    # If it is not the primary turn it on, if it is off
    if nic['mac_address'] != md['v1']['interfaces'][0]['mac']:
        prefix = "/" + to_cidr(nic['subnets'][0]['netmask'])
        ip = nic['subnets'][0]['address'] + prefix

        # Only use IP commands if they exist and this is Linux
        if util.is_Linux() and subp.which('ip'):
            bringup_nic_linux(nic, ip)

        # Only use ifconfig if this is BSD
        if util.is_BSD() and subp.which('ifconfig'):
            bringup_nic_bsd(nic, ip)


# Linux interface bring up procedure
def bringup_nic_linux(nic, ip):
    up = net.is_up(nic['name'])

    if up:
        LOGGER.debug("Flushing interface: %s" % nic['name'])

        command = ['ip', 'addr', 'flush', 'dev', nic['name']]
        try:
            subp.subp(command)
        except Exception as err:
            raise RuntimeError(
                "Command: %s failed to execute. Error: %s" %
                (" ".join(command), err))

    LOGGER.debug("Assigning IP: %s to interface: %s" %
                 (ip, nic['name']))
    command = ['ip', 'addr', 'add', ip, 'dev', nic['name']]
    try:
        subp.subp(command)
    except Exception as err:
        raise RuntimeError(
            "Command: %s failed to execute. Error: %s" %
            (" ".join(command), err))

    if not up:
        LOGGER.debug("Brining up interface: %s" % nic['name'])
        command = ['ip', 'link', 'set', 'dev', nic['name'], 'up']
        try:
            subp.subp(command)
        except Exception as err:
            raise RuntimeError(
                "Command: %s failed to execute. Error: %s" %
                (" ".join(command), err))


# BSD interface bring up procedure
def bringup_nic_bsd(nic, ip):
    up = net.is_up(nic['name'])

    LOGGER.debug("Assigning IP: %s to interface: %s" %
                 (ip, nic['name']))

    command = ['ifconfig', nic['name'], 'inet', ip]
    try:
        subp.subp(command)
    except Exception as err:
        raise RuntimeError(
            "Command: %s failed to execute. Error: %s" %
            (" ".join(command), err))

    if not up:
        command = ['ipconfig', nic['name'], 'up']
        try:
            subp.subp(command)
        except Exception as err:
            raise RuntimeError(
                "Command: %s failed to execute. Error: %s" %
                (" ".join(command), err))


# Process netcfg interfaces and bring additional up
def process_nics(netcfg, config):
    for config_op in netcfg['config']:
        if config_op['type'] == "physical":
            bringup_nic(config_op, config)


# Generate network configs
def generate_network_config(config):
    md = get_metadata(config)

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
    if len(md['v1']['interfaces']) > 0:
        network['config'].append(generate_public_network_interface(md))

    # Prepare interface 1, private
    if len(md['v1']['interfaces']) > 1:
        network['config'].append(generate_private_network_interface(md))

    return network


# Input Metadata and generate public network config part
def generate_public_network_interface(md):
    interface_name = get_interface_name(md['v1']['interfaces'][0]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system" %
            md['v1']['interfaces'][0]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": md['v1']['interfaces'][0]['mac'],
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
    additional_count = len(md['v1']['interfaces'][0]['ipv4']['additional'])
    if "ipv4" in md['v1']['interfaces'][0] and additional_count > 0:
        for additional in md['v1']['interfaces'][0]['ipv4']['additional']:
            add = {
                "type": "static",
                "control": "auto",
                "address": additional['address'],
                "netmask": additional['netmask']
            }
            netcfg['subnets'].append(add)

    # Check for additional IPv6's
    additional_count = len(md['v1']['interfaces'][0]['ipv6']['additional'])
    if "ipv6" in md['v1']['interfaces'][0] and additional_count > 0:
        for additional in md['v1']['interfaces'][0]['ipv6']['additional']:
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
    interface_name = get_interface_name(md['v1']['interfaces'][1]['mac'])
    if not interface_name:
        raise RuntimeError(
            "Interface: %s could not be found on the system"
            % md['v1']['interfaces'][1]['mac'])

    netcfg = {
        "name": interface_name,
        "type": "physical",
        "mac_address": md['v1']['interfaces'][1]['mac'],
        "accept-ra": 1,
        "subnets": [
            {
                "type": "static",
                "control": "auto",
                "address": md['v1']['interfaces'][1]['ipv4']['address'],
                "netmask": md['v1']['interfaces'][1]['ipv4']['netmask']
            }
        ]
    }

    return netcfg


# Generate the vendor config
# This configuration is to replicate how
# images are deployed on Vultr before Cloud-Init
def generate_config(config):
    md = get_metadata(config)

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
    vendor_script = []

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
                vendor_script.append(command)

    # Write vendor script
    write_vendor_script("vultr_deploy.sh", vendor_script)

    # Write the startup script
    if "No configured startup script" not in script:
        lines = script.split("\n")
        write_vendor_script("vultr_user_startup.sh", lines)

    return config_template


# vi: ts=4 expandtab
