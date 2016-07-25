# vi: ts=4 expandtab
#
#    Copyright (C) 2016 Canonical Ltd.
#
#    Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This module initializes lxd using 'lxd init'

Example config:
  #cloud-config
  lxd:
    init:
      network_address: <ip addr>
      network_port: <port>
      storage_backend: <zfs/dir>
      storage_create_device: <dev>
      storage_create_loop: <size>
      storage_pool: <name>
      trust_password: <password>
    bridge:
      mode: <new, existing or none>
      name: <name>
      ipv4_address: <ip addr>
      ipv4_netmask: <cidr>
      ipv4_dhcp_first: <ip addr>
      ipv4_dhcp_last: <ip addr>
      ipv4_dhcp_leases: <size>
      ipv4_nat: <bool>
      ipv6_address: <ip addr>
      ipv6_netmask: <cidr>
      ipv6_nat: <bool>
      domain: <domain>
"""

from cloudinit import util

distros = ['ubuntu']


def handle(name, cfg, cloud, log, args):
    # Get config
    lxd_cfg = cfg.get('lxd')
    if not lxd_cfg:
        log.debug("Skipping module named %s, not present or disabled by cfg",
                  name)
        return
    if not isinstance(lxd_cfg, dict):
        log.warn("lxd config must be a dictionary. found a '%s'",
                 type(lxd_cfg))
        return

    # Grab the configuration
    init_cfg = lxd_cfg.get('init')
    if not isinstance(init_cfg, dict):
        log.warn("lxd/init config must be a dictionary. found a '%s'",
                 type(init_cfg))
        init_cfg = {}

    bridge_cfg = lxd_cfg.get('bridge')
    if not isinstance(bridge_cfg, dict):
        log.warn("lxd/bridge config must be a dictionary. found a '%s'",
                 type(bridge_cfg))
        bridge_cfg = {}

    # Install the needed packages
    packages = []
    if not util.which("lxd"):
        packages.append('lxd')

    if init_cfg.get("storage_backend") == "zfs" and not util.which('zfs'):
        packages.append('zfs')

    if len(packages):
        try:
            cloud.distro.install_packages(packages)
        except util.ProcessExecutionError as exc:
            log.warn("failed to install packages %s: %s", packages, exc)
            return

    # Set up lxd if init config is given
    if init_cfg:
        init_keys = (
            'network_address', 'network_port', 'storage_backend',
            'storage_create_device', 'storage_create_loop',
            'storage_pool', 'trust_password')
        cmd = ['lxd', 'init', '--auto']
        for k in init_keys:
            if init_cfg.get(k):
                cmd.extend(["--%s=%s" %
                            (k.replace('_', '-'), str(init_cfg[k]))])
        util.subp(cmd)

    # Set up lxd-bridge if bridge config is given
    dconf_comm = "debconf-communicate"
    if bridge_cfg and util.which(dconf_comm):
        debconf = bridge_to_debconf(bridge_cfg)

        # Update debconf database
        try:
            log.debug("Setting lxd debconf via " + dconf_comm)
            data = "\n".join(["set %s %s" % (k, v)
                              for k, v in debconf.items()]) + "\n"
            util.subp(['debconf-communicate'], data)
        except Exception:
            util.logexc(log, "Failed to run '%s' for lxd with" % dconf_comm)

        # Remove the existing configuration file (forces re-generation)
        util.del_file("/etc/default/lxd-bridge")

        # Run reconfigure
        log.debug("Running dpkg-reconfigure for lxd")
        util.subp(['dpkg-reconfigure', 'lxd',
                   '--frontend=noninteractive'])
    elif bridge_cfg:
        raise RuntimeError(
            "Unable to configure lxd bridge without %s." + dconf_comm)


def bridge_to_debconf(bridge_cfg):
    debconf = {}

    if bridge_cfg.get("mode") == "none":
        debconf["lxd/setup-bridge"] = "false"
        debconf["lxd/bridge-name"] = ""

    elif bridge_cfg.get("mode") == "existing":
        debconf["lxd/setup-bridge"] = "false"
        debconf["lxd/use-existing-bridge"] = "true"
        debconf["lxd/bridge-name"] = bridge_cfg.get("name")

    elif bridge_cfg.get("mode") == "new":
        debconf["lxd/setup-bridge"] = "true"
        if bridge_cfg.get("name"):
            debconf["lxd/bridge-name"] = bridge_cfg.get("name")

        if bridge_cfg.get("ipv4_address"):
            debconf["lxd/bridge-ipv4"] = "true"
            debconf["lxd/bridge-ipv4-address"] = \
                bridge_cfg.get("ipv4_address")
            debconf["lxd/bridge-ipv4-netmask"] = \
                bridge_cfg.get("ipv4_netmask")
            debconf["lxd/bridge-ipv4-dhcp-first"] = \
                bridge_cfg.get("ipv4_dhcp_first")
            debconf["lxd/bridge-ipv4-dhcp-last"] = \
                bridge_cfg.get("ipv4_dhcp_last")
            debconf["lxd/bridge-ipv4-dhcp-leases"] = \
                bridge_cfg.get("ipv4_dhcp_leases")
            debconf["lxd/bridge-ipv4-nat"] = \
                bridge_cfg.get("ipv4_nat", "true")

        if bridge_cfg.get("ipv6_address"):
            debconf["lxd/bridge-ipv6"] = "true"
            debconf["lxd/bridge-ipv6-address"] = \
                bridge_cfg.get("ipv6_address")
            debconf["lxd/bridge-ipv6-netmask"] = \
                bridge_cfg.get("ipv6_netmask")
            debconf["lxd/bridge-ipv6-nat"] = \
                bridge_cfg.get("ipv6_nat", "false")

        if bridge_cfg.get("domain"):
            debconf["lxd/bridge-domain"] = bridge_cfg.get("domain")

    else:
        raise Exception("invalid bridge mode \"%s\"" % bridge_cfg.get("mode"))

    return debconf
