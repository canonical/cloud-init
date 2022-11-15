# (c) Copyright IBM Corp. 2020 All Rights Reserved
#
# Author: Aman Kumar Sinha <amansi26@in.ibm.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Refresh IPv6 interface and RMC:
Ensure Network Manager is not managing IPv6 interface"""

import errno
from logging import Logger

from cloudinit import log as logging
from cloudinit import netinfo, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

MODULE_DESCRIPTION = """\
This module is IBM PowerVM Hypervisor specific

Reliable Scalable Cluster Technology (RSCT) is a set of software components
that together provide a comprehensive clustering environment(RAS features)
for IBM PowerVM based virtual machines. RSCT includes the Resource
Monitoring and Control (RMC) subsystem. RMC is a generalized framework used
for managing, monitoring, and manipulating resources. RMC runs as a daemon
process on individual machines and needs creation of unique node id and
restarts during VM boot.
More details refer
https://www.ibm.com/support/knowledgecenter/en/SGVKBA_3.2/admin/bl503_ovrv.htm

This module handles
- Refreshing RMC
- Disabling NetworkManager from handling IPv6 interface, as IPv6 interface
  is used for communication between RMC daemon and PowerVM hypervisor.
"""

meta: MetaSchema = {
    "id": "cc_refresh_rmc_and_interface",
    "name": "Refresh IPv6 Interface and RMC",
    "title": "Ensure Network Manager is not managing IPv6 interface",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_ALWAYS,
    "examples": [],
    "activate_by_schema_keys": [],
}

# This module is undocumented in our schema docs
__doc__ = ""

LOG = logging.getLogger(__name__)
# Ensure that /opt/rsct/bin has been added to standard PATH of the
# distro. The symlink to rmcctrl is /usr/sbin/rsct/bin/rmcctrl .
RMCCTRL = "rmcctrl"


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if not subp.which(RMCCTRL):
        LOG.debug("No '%s' in path, disabled", RMCCTRL)
        return

    LOG.debug(
        "Making the IPv6 up explicitly. "
        "Ensuring IPv6 interface is not being handled by NetworkManager "
        "and it is  restarted to re-establish the communication with "
        "the hypervisor"
    )

    ifaces = find_ipv6_ifaces()

    # Setting NM_CONTROLLED=no for IPv6 interface
    # making it down and up

    if len(ifaces) == 0:
        LOG.debug("Did not find any interfaces with ipv6 addresses.")
    else:
        for iface in ifaces:
            refresh_ipv6(iface)
            disable_ipv6(sysconfig_path(iface))
        restart_network_manager()


def find_ipv6_ifaces():
    info = netinfo.netdev_info()
    ifaces = []
    for iface, data in info.items():
        if iface == "lo":
            LOG.debug("Skipping localhost interface")
        if len(data.get("ipv4", [])) != 0:
            # skip this interface, as it has ipv4 addrs
            continue
        ifaces.append(iface)
    return ifaces


def refresh_ipv6(interface):
    # IPv6 interface is explicitly brought up, subsequent to which the
    # RMC services are restarted to re-establish the communication with
    # the hypervisor.
    subp.subp(["ip", "link", "set", interface, "down"])
    subp.subp(["ip", "link", "set", interface, "up"])


def sysconfig_path(iface):
    return "/etc/sysconfig/network-scripts/ifcfg-" + iface


def restart_network_manager():
    subp.subp(["systemctl", "restart", "NetworkManager"])


def disable_ipv6(iface_file):
    # Ensuring that the communication b/w the hypervisor and VM is not
    # interrupted due to NetworkManager. For this purpose, as part of
    # this function, the NM_CONTROLLED is explicitly set to No for IPV6
    # interface and NetworkManager is restarted.
    try:
        contents = util.load_file(iface_file)
    except IOError as e:
        if e.errno == errno.ENOENT:
            LOG.debug("IPv6 interface file %s does not exist\n", iface_file)
        else:
            raise e

    if "IPV6INIT" not in contents:
        LOG.debug("Interface file %s did not have IPV6INIT", iface_file)
        return

    LOG.debug("Editing interface file %s ", iface_file)

    # Dropping any NM_CONTROLLED or IPV6 lines from IPv6 interface file.
    lines = contents.splitlines()
    lines = [line for line in lines if not search(line)]
    lines.append("NM_CONTROLLED=no")

    with open(iface_file, "w") as fp:
        fp.write("\n".join(lines) + "\n")


def search(contents):
    # Search for any NM_CONTROLLED or IPV6 lines in IPv6 interface file.
    return (
        contents.startswith("IPV6ADDR")
        or contents.startswith("IPADDR6")
        or contents.startswith("IPV6INIT")
        or contents.startswith("NM_CONTROLLED")
    )


def refresh_rmc():
    # To make a healthy connection between RMC daemon and hypervisor we
    # refresh RMC. With refreshing RMC we are ensuring that making IPv6
    # down and up shouldn't impact communication between RMC daemon and
    # hypervisor.
    # -z : stop Resource Monitoring & Control subsystem and all resource
    # managers, but the command does not return control to the user
    # until the subsystem and all resource managers are stopped.
    # -s : start Resource Monitoring & Control subsystem.
    try:
        subp.subp([RMCCTRL, "-z"])
        subp.subp([RMCCTRL, "-s"])
    except Exception:
        util.logexc(LOG, "Failed to refresh the RMC subsystem.")
        raise
