# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json

import os
from os import path
import base64

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
    "startup-script": "/latest/startup-script",
    "hostname": "/latest/meta-data/hostname",
    "user-data": "/latest/user-data",
    "mdisk-mode": "/v1/internal/mdisk-mode",
    "root-password": "/v1/internal/root-password",
    "ssh-keys": "/current/ssh-keys",
    "ipv6-dns1": "/current/ipv6-dns1",
    "ipv6-addr": "/current/meta-data/ipv6-addr",
    "v1.json": "/v1.json",
    "disable_ssh_login": "/v1/internal/md-disable_ssh_login"
}


# Cache
MAC_TO_NICS = None
METADATA = None


# Cache the metadata for optimization
def get_metadata(params):
    global METADATA

    if not METADATA:
        METADATA = {
            'startup-script': fetch_metadata("startup-script", params),
            'hostname': fetch_metadata("hostname", params),
            'user-data': fetch_metadata("user-data", params),
            'mdisk-mode': fetch_metadata("mdisk-mode", params),
            'root-password': fetch_metadata("root-password", params),
            'ssh-keys': fetch_metadata("ssh-keys", params),
            'ipv6-dns1': fetch_metadata("ipv6-dns1", params),
            'ipv6-addr': fetch_metadata("ipv6-addr", params),
            'v1': json.loads(fetch_metadata("v1.json", params))
            #    'disable_ssh_login': fetch_metadata("disable_ssh_login", params),
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
    if not path.exists("/proc/cmdline"):
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
    if path.exists("/etc/vultr") and path.isdir("/etc/vultr"):
        return True

    return False


# Read cached network config
def get_cached_network_config():
    os.makedirs("/etc/vultr/cache/", exist_ok=True)
    content = ""
    fname = "/etc/vultr/cache/network"
    if path.exists(fname):
        file = open(fname, "r")
        content = file.read()
        file.close()
    return content


# Cached network config
def cache_network_config(config):
    os.makedirs("/etc/vultr/cache/", exist_ok=True)
    file = open("/etc/vultr/cache/network", "w")
    file.write(json.dumps(config))
    file.close()


# Write vendor startup script
def write_vendor_script(fname, content):
    os.makedirs("/var/lib/scripts/vendor/", exist_ok=True)
    file = open("/var/lib/scripts/vendor/%s" % fname, "w")
    file.write("#!/bin/bash")
    for line in content:
        file.write(line)
    file.close()
    run_system_command(
        ["chmod", "+x", "/var/lib/scripts/vendor/%s" % fname], False)


# Read Metadata endpoint
def read_metadata(params):
    response = url_helper.readurl(params['url'], timeout=params['timeout'], retries=params['retries'],
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

    if "app-" in flag or "md-" in flag:
        return url + "/v1/internal/" + flag

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


# Run system commands and handle errors
def run_system_command(command, allow_fail=True):
    try:
        subp.subp(command)
    except Exception as err:
        if not allow_fail:
            raise RuntimeError(
                "Command: %s failed to execute. Error: %s" % (" ".join(command), err))
        LOGGER.debug("Command: %s failed to execute. Error: %s" %
                     (" ".join(command), err))
        return False
    return True


# Cloud-init does not support turning on any interface beyond
# the first. The repercussions being there is no stable and
# appropriate way to enable critical interfaces. This hack,
# though functional, will have minimal support and break easily.
def bringup_nic(nic, config, toggle=False):
    # Dont act if not toggling and it interface is up
    if not toggle and net.is_up(nic['name']):
        return

    md = get_metadata(config)

    # If it is not the primary turn it on, if it is off
    if nic['mac_address'] != md['v1']['interfaces'][0]['mac']:
        prefix = "/" + str(sum(bin(int(x)).count('1')
                               for x in nic['subnets'][0]['netmask'].split('.')))
        ip = nic['subnets'][0]['address'] + prefix

        # Only use IP commands if they exist and this is Linux
        if util.is_Linux() and subp.which('ip'):
            bringup_nic_linux(nic, ip, toggle)

        # Only use ifconfig if this is BSD
        if util.is_BSD() and subp.which('ifconfig'):
            bringup_nic_bsd(nic, ip, toggle)


def bringup_nic_linux(nic, ip, toggle=False):
    # Toggle interface if up
    if toggle and net.is_up(nic['name']):
        LOGGER.debug("Brining down interface: %s" % nic['name'])
        if not run_system_command(['ip', 'link', 'set', 'dev', nic['name'], 'down']):
            LOGGER.debug(
                "Failed brining down interface: %s" % nic['name'])
            return

    LOGGER.debug("Assigning IP: %s to interface: %s" %
                 (ip, nic['name']))
    if not run_system_command(['ip', 'addr', 'add', ip, 'dev', nic['name']]):
        LOGGER.debug(
            "Failed assigning IP: %s to interface: %s" % (ip, nic['name']))
        return

    LOGGER.debug("Brining up interface: %s" % nic['name'])
    run_system_command(['ip', 'link', 'set', 'dev', nic['name'], 'up'])


def bringup_nic_bsd(nic, ip, toggle=False):
    # Toggle interface if up
    if toggle and net.is_up(nic['name']):
        LOGGER.debug("Brining down interface: %s" % nic['name'])
        if not run_system_command(['ifconfig', nic['name'], 'down']):
            LOGGER.debug(
                "Failed brining down interface: %s" % nic['name'])
            return

    LOGGER.debug("Assigning IP: %s to interface: %s" %
                 (ip, nic['name']))
    if run_system_command(['ifconfig', nic['name'], 'inet', ip]):
        LOGGER.debug(
            "Failed assigning IP: %s to interface: %s" % (ip, nic['name']))
        return

    LOGGER.debug("Brining up interface: %s" % nic['name'])
    run_system_command(['ipconfig', nic['name'], 'up'])


# Process netcfg interfaces and bring additional up
def process_nics(netcfg, config, toggle=False):
    for config_op in netcfg['config']:
        if config_op['type'] == "physical":
            bringup_nic(config_op, toggle)


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
            "Interface: %s could not be found on the system" % md['v1']['interfaces'][0]['mac'])

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
    if "ipv4" in md['v1']['interfaces'][0] and len(md['v1']['interfaces'][0]['ipv4']['additional']) > 0:
        for additional in md['v1']['interfaces'][0]['ipv4']['additional']:
            add = {
                "type": "static",
                "control": "auto",
                "address": additional['address'],
                "netmask": additional['netmask']
            }
            netcfg['subnets'].append(add)

    # Check for additional IPv6's
    if "ipv6" in md['v1']['interfaces'][0] and len(md['v1']['interfaces'][0]['ipv6']['additional']) > 0:
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
            "Interface: %s could not be found on the system" % md['v1']['interfaces'][1]['mac'])

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
    if script != "":
        script = base64.b64encode(
            script.encode("ascii")).decode("ascii")

    # Grab the rest of the details
    rootpw = md['root-password']

    sshlogin = "no"
    if 'disable_ssh_login' in md:
        sshlogin = md['disable_ssh_login']

    # Start the template
    # We currently setup root, this will eventually change
    config_template = {
        "package_upgrade": "true",
        "disable_root": 0,
        "packages": [],
        "ssh_pwauth": 1,
        "chpasswd": {
            "expire": False,
            "list": [
                "root:" + rootpw
            ]
        },
        "system_info": {
            "default_user": {
                "name": "root"
            }
        },
        "network": generate_network_config(config)
    }

    # Settings
    if sshlogin == "yes":
        config_template['ssh_pwauth'] = False

    # Linux specific packages
    if util.is_Linux():
        config_template["packages"].append("ethtool")

    # Define vendor script
    vendor_script = []

    # Go through the interfaces
    for netcfg in config_template['network']['config']:
        # If the adapter has a name and is physical
        if "mac_address" in netcfg and netcfg['type'] == "physical":
            # Cloud-init does not support configuring multi-queue on
            # interfaces. A specialized tool needs to be used to enable
            # this critical functionality in a universal and predictable way.
            # This hack though functional, will have minimal support and break easily.

            # Enable multi-queue on linux
            # This needs to remain a runcmd as the package may not be installed
            if util.is_Linux():
                # Set its multi-queue to num of cores as per RHEL Docs
                vendor_script.append(
                    "ethtool -L " + netcfg['name'] + " combined $(nproc --all)")

    # Write vendor script
    write_vendor_script("vultr_deploy.sh", vendor_script)

    # Write the startup script
    if script != "":
        ba = script.encode('ascii')
        ba_dec = base64.b64decode(ba)
        lines = ba_dec.decode('ascii').split("\n")
        write_vendor_script("vultr_user_startup.sh", lines)

    return config_template


# vi: ts=4 expandtab
