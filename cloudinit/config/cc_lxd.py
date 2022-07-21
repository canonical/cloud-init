# Copyright (C) 2016 Canonical Ltd.
#
# Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""LXD: configure lxd with ``lxd init`` and optionally lxd-bridge"""

import os
from textwrap import dedent
from typing import List

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

_DEFAULT_NETWORK_NAME = "lxdbr0"


MODULE_DESCRIPTION = """\
This module configures lxd with user specified options using ``lxd init``.
If lxd is not present on the system but lxd configuration is provided, then
lxd will be installed. If the selected storage backend userspace utility is
not installed, it will be installed. If network bridge configuration is
provided, then lxd-bridge will be configured accordingly.
"""

distros = ["ubuntu"]

meta: MetaSchema = {
    "id": "cc_lxd",
    "name": "LXD",
    "title": "Configure LXD with ``lxd init`` and optionally lxd-bridge",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
            # Simplest working directory backed LXD configuration
            lxd:
              init:
                storage_backend: dir
            """
        ),
        dedent(
            """\
            lxd:
              init:
                network_address: 0.0.0.0
                network_port: 8443
                storage_backend: zfs
                storage_pool: datapool
                storage_create_loop: 10
              bridge:
                mode: new
                name: lxdbr0
                ipv4_address: 10.0.8.1
                ipv4_netmask: 24
                ipv4_dhcp_first: 10.0.8.2
                ipv4_dhcp_last: 10.0.8.3
                ipv4_dhcp_leases: 250
                ipv4_nat: true
                ipv6_address: fd98:9e0:3744::1
                ipv6_netmask: 64
                ipv6_nat: true
                domain: lxd
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["lxd"],
}

__doc__ = get_meta_doc(meta)


def handle(name, cfg, cloud, log, args):
    # Get config
    lxd_cfg = cfg.get("lxd")
    if not lxd_cfg:
        log.debug(
            "Skipping module named %s, not present or disabled by cfg", name
        )
        return
    if not isinstance(lxd_cfg, dict):
        log.warning(
            "lxd config must be a dictionary. found a '%s'", type(lxd_cfg)
        )
        return

    # Grab the configuration
    init_cfg = lxd_cfg.get("init")
    if not isinstance(init_cfg, dict):
        log.warning(
            "lxd/init config must be a dictionary. found a '%s'",
            type(init_cfg),
        )
        init_cfg = {}

    bridge_cfg = lxd_cfg.get("bridge", {})
    if not isinstance(bridge_cfg, dict):
        log.warning(
            "lxd/bridge config must be a dictionary. found a '%s'",
            type(bridge_cfg),
        )
        bridge_cfg = {}
    packages = get_required_packages(init_cfg)
    if len(packages):
        try:
            cloud.distro.install_packages(packages)
        except subp.ProcessExecutionError as exc:
            log.warning("failed to install packages %s: %s", packages, exc)
            return

    # Set up lxd if init config is given
    if init_cfg:
        init_keys = (
            "network_address",
            "network_port",
            "storage_backend",
            "storage_create_device",
            "storage_create_loop",
            "storage_pool",
            "trust_password",
        )
        subp.subp(["lxd", "waitready", "--timeout=300"])
        cmd = ["lxd", "init", "--auto"]
        for k in init_keys:
            if init_cfg.get(k):
                cmd.extend(
                    ["--%s=%s" % (k.replace("_", "-"), str(init_cfg[k]))]
                )
        subp.subp(cmd)

    # Set up lxd-bridge if bridge config is given
    dconf_comm = "debconf-communicate"
    if bridge_cfg:
        net_name = bridge_cfg.get("name", _DEFAULT_NETWORK_NAME)
        if os.path.exists("/etc/default/lxd-bridge") and subp.which(
            dconf_comm
        ):
            # Bridge configured through packaging

            debconf = bridge_to_debconf(bridge_cfg)

            # Update debconf database
            try:
                log.debug("Setting lxd debconf via " + dconf_comm)
                data = (
                    "\n".join(
                        ["set %s %s" % (k, v) for k, v in debconf.items()]
                    )
                    + "\n"
                )
                subp.subp(["debconf-communicate"], data)
            except Exception:
                util.logexc(
                    log, "Failed to run '%s' for lxd with" % dconf_comm
                )

            # Remove the existing configuration file (forces re-generation)
            util.del_file("/etc/default/lxd-bridge")

            # Run reconfigure
            log.debug("Running dpkg-reconfigure for lxd")
            subp.subp(["dpkg-reconfigure", "lxd", "--frontend=noninteractive"])
        else:
            # Built-in LXD bridge support
            cmd_create, cmd_attach = bridge_to_cmd(bridge_cfg)
            maybe_cleanup_default(
                net_name=net_name,
                did_init=bool(init_cfg),
                create=bool(cmd_create),
                attach=bool(cmd_attach),
            )
            if cmd_create:
                log.debug("Creating lxd bridge: %s" % " ".join(cmd_create))
                _lxc(cmd_create)

            if cmd_attach:
                log.debug(
                    "Setting up default lxd bridge: %s" % " ".join(cmd_attach)
                )
                _lxc(cmd_attach)

    elif bridge_cfg:
        raise RuntimeError(
            "Unable to configure lxd bridge without %s." + dconf_comm
        )


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
            debconf["lxd/bridge-ipv4-address"] = bridge_cfg.get("ipv4_address")
            debconf["lxd/bridge-ipv4-netmask"] = bridge_cfg.get("ipv4_netmask")
            debconf["lxd/bridge-ipv4-dhcp-first"] = bridge_cfg.get(
                "ipv4_dhcp_first"
            )
            debconf["lxd/bridge-ipv4-dhcp-last"] = bridge_cfg.get(
                "ipv4_dhcp_last"
            )
            debconf["lxd/bridge-ipv4-dhcp-leases"] = bridge_cfg.get(
                "ipv4_dhcp_leases"
            )
            debconf["lxd/bridge-ipv4-nat"] = bridge_cfg.get("ipv4_nat", "true")

        if bridge_cfg.get("ipv6_address"):
            debconf["lxd/bridge-ipv6"] = "true"
            debconf["lxd/bridge-ipv6-address"] = bridge_cfg.get("ipv6_address")
            debconf["lxd/bridge-ipv6-netmask"] = bridge_cfg.get("ipv6_netmask")
            debconf["lxd/bridge-ipv6-nat"] = bridge_cfg.get(
                "ipv6_nat", "false"
            )

        if bridge_cfg.get("domain"):
            debconf["lxd/bridge-domain"] = bridge_cfg.get("domain")

    else:
        raise Exception('invalid bridge mode "%s"' % bridge_cfg.get("mode"))

    return debconf


def bridge_to_cmd(bridge_cfg):
    if bridge_cfg.get("mode") == "none":
        return None, None

    bridge_name = bridge_cfg.get("name", _DEFAULT_NETWORK_NAME)
    cmd_create = []
    cmd_attach = ["network", "attach-profile", bridge_name, "default", "eth0"]

    if bridge_cfg.get("mode") == "existing":
        return None, cmd_attach

    if bridge_cfg.get("mode") != "new":
        raise Exception('invalid bridge mode "%s"' % bridge_cfg.get("mode"))

    cmd_create = ["network", "create", bridge_name]

    if bridge_cfg.get("ipv4_address") and bridge_cfg.get("ipv4_netmask"):
        cmd_create.append(
            "ipv4.address=%s/%s"
            % (bridge_cfg.get("ipv4_address"), bridge_cfg.get("ipv4_netmask"))
        )

        if bridge_cfg.get("ipv4_nat", "true") == "true":
            cmd_create.append("ipv4.nat=true")

        if bridge_cfg.get("ipv4_dhcp_first") and bridge_cfg.get(
            "ipv4_dhcp_last"
        ):
            dhcp_range = "%s-%s" % (
                bridge_cfg.get("ipv4_dhcp_first"),
                bridge_cfg.get("ipv4_dhcp_last"),
            )
            cmd_create.append("ipv4.dhcp.ranges=%s" % dhcp_range)
    else:
        cmd_create.append("ipv4.address=none")

    if bridge_cfg.get("ipv6_address") and bridge_cfg.get("ipv6_netmask"):
        cmd_create.append(
            "ipv6.address=%s/%s"
            % (bridge_cfg.get("ipv6_address"), bridge_cfg.get("ipv6_netmask"))
        )

        if bridge_cfg.get("ipv6_nat", "false") == "true":
            cmd_create.append("ipv6.nat=true")

    else:
        cmd_create.append("ipv6.address=none")

    if bridge_cfg.get("domain"):
        cmd_create.append("dns.domain=%s" % bridge_cfg.get("domain"))

    return cmd_create, cmd_attach


def _lxc(cmd):
    env = {
        "LC_ALL": "C",
        "HOME": os.environ.get("HOME", "/root"),
        "USER": os.environ.get("USER", "root"),
    }
    subp.subp(["lxc"] + list(cmd) + ["--force-local"], update_env=env)


def maybe_cleanup_default(
    net_name, did_init, create, attach, profile="default", nic_name="eth0"
):
    """Newer versions of lxc (3.0.1+) create a lxdbr0 network when
    'lxd init --auto' is run.  Older versions did not.

    By removing any that lxd-init created, we simply leave the add/attach
    code intact.

    https://github.com/lxc/lxd/issues/4649"""
    if net_name != _DEFAULT_NETWORK_NAME or not did_init:
        return

    fail_assume_enoent = "failed. Assuming it did not exist."
    succeeded = "succeeded."
    if create:
        msg = "Detach of lxd network '%s' from profile '%s' %s"
        try:
            _lxc(["network", "detach-profile", net_name, profile])
            LOG.debug(msg, net_name, profile, succeeded)
        except subp.ProcessExecutionError as e:
            if e.exit_code != 1:
                raise e
            LOG.debug(msg, net_name, profile, fail_assume_enoent)
        else:
            msg = "Deletion of lxd network '%s' %s"
            _lxc(["network", "delete", net_name])
            LOG.debug(msg, net_name, succeeded)

    if attach:
        msg = "Removal of device '%s' from profile '%s' %s"
        try:
            _lxc(["profile", "device", "remove", profile, nic_name])
            LOG.debug(msg, nic_name, profile, succeeded)
        except subp.ProcessExecutionError as e:
            if e.exit_code != 1:
                raise e
            LOG.debug(msg, nic_name, profile, fail_assume_enoent)


def get_required_packages(cfg: dict) -> List[str]:
    """identify required packages for install"""
    packages = []
    if not subp.which("lxd"):
        packages.append("lxd")

    # binary for pool creation must be available for the requested backend:
    # zfs, lvcreate, mkfs.btrfs
    storage: str = cfg.get("storage_backend", "")
    if storage:
        if storage == "zfs" and not subp.which("zfs"):
            packages.append("zfsutils-linux")
        if storage == "lvm" and not subp.which("lvcreate"):
            packages.append("lvm2")
        if storage == "btrfs" and not subp.which("mkfs.btrfs"):
            packages.append("btrfs-progs")
    return packages
