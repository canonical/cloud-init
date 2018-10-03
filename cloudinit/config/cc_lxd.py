# Copyright (C) 2016 Canonical Ltd.
#
# Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
LXD
---
**Summary:** configure lxd with ``lxd init`` and optionally lxd-bridge

This module configures lxd with user specified options using ``lxd init``.
If lxd is not present on the system but lxd configuration is provided, then
lxd will be installed. If the selected storage backend is zfs, then zfs will
be installed if missing. If network bridge configuration is provided, then
lxd-bridge will be configured accordingly.

**Internal name:** ``cc_lxd``

**Module frequency:** per instance

**Supported distros:** ubuntu

**Config keys**::

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

from cloudinit import log as logging
from cloudinit import util
import os

distros = ['ubuntu']

LOG = logging.getLogger(__name__)

_DEFAULT_NETWORK_NAME = "lxdbr0"


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

    bridge_cfg = lxd_cfg.get('bridge', {})
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
        util.subp(['lxd', 'waitready', '--timeout=300'])
        cmd = ['lxd', 'init', '--auto']
        for k in init_keys:
            if init_cfg.get(k):
                cmd.extend(["--%s=%s" %
                            (k.replace('_', '-'), str(init_cfg[k]))])
        util.subp(cmd)

    # Set up lxd-bridge if bridge config is given
    dconf_comm = "debconf-communicate"
    if bridge_cfg:
        net_name = bridge_cfg.get("name", _DEFAULT_NETWORK_NAME)
        if os.path.exists("/etc/default/lxd-bridge") \
                and util.which(dconf_comm):
            # Bridge configured through packaging

            debconf = bridge_to_debconf(bridge_cfg)

            # Update debconf database
            try:
                log.debug("Setting lxd debconf via " + dconf_comm)
                data = "\n".join(["set %s %s" % (k, v)
                                  for k, v in debconf.items()]) + "\n"
                util.subp(['debconf-communicate'], data)
            except Exception:
                util.logexc(log, "Failed to run '%s' for lxd with" %
                            dconf_comm)

            # Remove the existing configuration file (forces re-generation)
            util.del_file("/etc/default/lxd-bridge")

            # Run reconfigure
            log.debug("Running dpkg-reconfigure for lxd")
            util.subp(['dpkg-reconfigure', 'lxd',
                       '--frontend=noninteractive'])
        else:
            # Built-in LXD bridge support
            cmd_create, cmd_attach = bridge_to_cmd(bridge_cfg)
            maybe_cleanup_default(
                net_name=net_name, did_init=bool(init_cfg),
                create=bool(cmd_create), attach=bool(cmd_attach))
            if cmd_create:
                log.debug("Creating lxd bridge: %s" %
                          " ".join(cmd_create))
                _lxc(cmd_create)

            if cmd_attach:
                log.debug("Setting up default lxd bridge: %s" %
                          " ".join(cmd_create))
                _lxc(cmd_attach)

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


def bridge_to_cmd(bridge_cfg):
    if bridge_cfg.get("mode") == "none":
        return None, None

    bridge_name = bridge_cfg.get("name", _DEFAULT_NETWORK_NAME)
    cmd_create = []
    cmd_attach = ["network", "attach-profile", bridge_name,
                  "default", "eth0"]

    if bridge_cfg.get("mode") == "existing":
        return None, cmd_attach

    if bridge_cfg.get("mode") != "new":
        raise Exception("invalid bridge mode \"%s\"" % bridge_cfg.get("mode"))

    cmd_create = ["network", "create", bridge_name]

    if bridge_cfg.get("ipv4_address") and bridge_cfg.get("ipv4_netmask"):
        cmd_create.append("ipv4.address=%s/%s" %
                          (bridge_cfg.get("ipv4_address"),
                           bridge_cfg.get("ipv4_netmask")))

        if bridge_cfg.get("ipv4_nat", "true") == "true":
            cmd_create.append("ipv4.nat=true")

        if bridge_cfg.get("ipv4_dhcp_first") and \
                bridge_cfg.get("ipv4_dhcp_last"):
            dhcp_range = "%s-%s" % (bridge_cfg.get("ipv4_dhcp_first"),
                                    bridge_cfg.get("ipv4_dhcp_last"))
            cmd_create.append("ipv4.dhcp.ranges=%s" % dhcp_range)
    else:
        cmd_create.append("ipv4.address=none")

    if bridge_cfg.get("ipv6_address") and bridge_cfg.get("ipv6_netmask"):
        cmd_create.append("ipv6.address=%s/%s" %
                          (bridge_cfg.get("ipv6_address"),
                           bridge_cfg.get("ipv6_netmask")))

        if bridge_cfg.get("ipv6_nat", "false") == "true":
            cmd_create.append("ipv6.nat=true")

    else:
        cmd_create.append("ipv6.address=none")

    if bridge_cfg.get("domain"):
        cmd_create.append("dns.domain=%s" % bridge_cfg.get("domain"))

    return cmd_create, cmd_attach


def _lxc(cmd):
    env = {'LC_ALL': 'C',
           'HOME': os.environ.get('HOME', '/root'),
           'USER': os.environ.get('USER', 'root')}
    util.subp(['lxc'] + list(cmd) + ["--force-local"], update_env=env)


def maybe_cleanup_default(net_name, did_init, create, attach,
                          profile="default", nic_name="eth0"):
    """Newer versions of lxc (3.0.1+) create a lxdbr0 network when
    'lxd init --auto' is run.  Older versions did not.

    By removing ay that lxd-init created, we simply leave the add/attach
    code in-tact.

    https://github.com/lxc/lxd/issues/4649"""
    if net_name != _DEFAULT_NETWORK_NAME or not did_init:
        return

    fail_assume_enoent = "failed. Assuming it did not exist."
    succeeded = "succeeded."
    if create:
        msg = "Deletion of lxd network '%s' %s"
        try:
            _lxc(["network", "delete", net_name])
            LOG.debug(msg, net_name, succeeded)
        except util.ProcessExecutionError as e:
            if e.exit_code != 1:
                raise e
            LOG.debug(msg, net_name, fail_assume_enoent)

    if attach:
        msg = "Removal of device '%s' from profile '%s' %s"
        try:
            _lxc(["profile", "device", "remove", profile, nic_name])
            LOG.debug(msg, nic_name, profile, succeeded)
        except util.ProcessExecutionError as e:
            if e.exit_code != 1:
                raise e
            LOG.debug(msg, nic_name, profile, fail_assume_enoent)


# vi: ts=4 expandtab
