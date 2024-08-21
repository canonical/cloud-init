# Copyright (C) 2016 Canonical Ltd.
#
# Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""LXD: configure lxd with ``lxd init`` and optionally lxd-bridge"""

import logging
import os
from typing import List, Tuple

import yaml

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

_DEFAULT_NETWORK_NAME = "lxdbr0"

meta: MetaSchema = {
    "id": "cc_lxd",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["lxd"],
}  # type: ignore


def supplemental_schema_validation(init_cfg, bridge_cfg, preseed_str):
    """Validate user-provided lxd network and bridge config option values.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    if not isinstance(init_cfg, dict):
        errors.append(
            f"lxd.init config must be a dictionary. found a"
            f" '{type(init_cfg).__name__}'",
        )

    if not isinstance(bridge_cfg, dict):
        errors.append(
            f"lxd.bridge config must be a dictionary. found a"
            f" '{type(bridge_cfg).__name__}'",
        )

    if not isinstance(preseed_str, str):
        errors.append(
            f"lxd.preseed config must be a string. found a"
            f" '{type(preseed_str).__name__}'",
        )
    if preseed_str and (init_cfg or bridge_cfg):
        incompat_cfg = ["lxd.init"] if init_cfg else []
        incompat_cfg += ["lxd.bridge"] if bridge_cfg else []

        errors.append(
            "Unable to configure LXD. lxd.preseed config can not be provided"
            f" with key(s): {', '.join(incompat_cfg)}"
        )
    if errors:
        raise ValueError(". ".join(errors))


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # Get config
    lxd_cfg = cfg.get("lxd")
    if not lxd_cfg:
        LOG.debug(
            "Skipping module named %s, not present or disabled by cfg", name
        )
        return
    if not isinstance(lxd_cfg, dict):
        raise ValueError(
            f"lxd config must be a dictionary. found a"
            f" '{type(lxd_cfg).__name__}'"
        )

    util.wait_for_snap_seeded(cloud)
    # Grab the configuration
    init_cfg = lxd_cfg.get("init", {})
    preseed_str = lxd_cfg.get("preseed", "")
    bridge_cfg = lxd_cfg.get("bridge", {})
    supplemental_schema_validation(init_cfg, bridge_cfg, preseed_str)

    if not subp.which("lxd"):
        try:
            subp.subp(["snap", "install", "lxd"])
        except subp.ProcessExecutionError as e:
            raise RuntimeError(
                "Failed to install lxd from snap: %s" % e
            ) from e
    packages = get_required_packages(init_cfg, preseed_str)
    if len(packages):
        try:
            cloud.distro.install_packages(packages)
        except subp.ProcessExecutionError as exc:
            LOG.warning("failed to install packages %s: %s", packages, exc)
            return

    subp.subp(["lxd", "waitready", "--timeout=300"])
    if preseed_str:
        subp.subp(["lxd", "init", "--preseed"], data=preseed_str)
        return
    # Set up lxd if init config is given
    if init_cfg:
        # type is known, number of elements is not
        # in the case of the ubuntu+lvm backend workaround
        init_keys: Tuple[str, ...] = (
            "network_address",
            "network_port",
            "storage_backend",
            "storage_create_device",
            "storage_create_loop",
            "storage_pool",
            "trust_password",
        )

        # Bug https://bugs.launchpad.net/ubuntu/+source/linux-kvm/+bug/1982780
        kernel = util.system_info()["uname"][2]
        if init_cfg["storage_backend"] == "lvm" and not os.path.exists(
            f"/lib/modules/{kernel}/kernel/drivers/md/dm-thin-pool.ko"
        ):
            LOG.warning(
                "cloud-init doesn't use thinpool by default on Ubuntu due to "
                "LP #1982780. This behavior will change in the future.",
            )
            subp.subp(
                [
                    "lxc",
                    "storage",
                    "create",
                    "default",
                    "lvm",
                    "lvm.use_thinpool=false",
                ]
            )

            # Since we're manually setting use_thinpool=false
            # filter it from the lxd init commands, don't configure
            # storage twice
            init_keys = tuple(
                key for key in init_keys if key != "storage_backend"
            )

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
                LOG.debug("Setting lxd debconf via %s", dconf_comm)
                data = (
                    "\n".join(
                        ["set %s %s" % (k, v) for k, v in debconf.items()]
                    )
                    + "\n"
                )
                subp.subp(["debconf-communicate"], data=data)
            except Exception:
                util.logexc(
                    LOG, "Failed to run '%s' for lxd with" % dconf_comm
                )

            # Remove the existing configuration file (forces re-generation)
            util.del_file("/etc/default/lxd-bridge")

            # Run reconfigure
            LOG.debug("Running dpkg-reconfigure for lxd")
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
                LOG.debug("Creating lxd bridge: %s", " ".join(cmd_create))
                _lxc(cmd_create)

            if cmd_attach:
                LOG.debug(
                    "Setting up default lxd bridge: %s", " ".join(cmd_attach)
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
        raise RuntimeError('invalid bridge mode "%s"' % bridge_cfg.get("mode"))

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
        raise RuntimeError('invalid bridge mode "%s"' % bridge_cfg.get("mode"))

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

        if bridge_cfg.get("ipv6_nat") == "true":
            cmd_create.append("ipv6.nat=true")

    else:
        cmd_create.append("ipv6.address=none")

    if bridge_cfg.get("domain"):
        cmd_create.append("dns.domain=%s" % bridge_cfg.get("domain"))

    # if the default schema value is passed (-1) don't pass arguments
    # to LXD. Use LXD defaults unless user manually sets a number
    mtu = bridge_cfg.get("mtu", -1)
    if mtu != -1:
        cmd_create.append(f"bridge.mtu={mtu}")

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

    https://github.com/canonical/lxd/issues/4649"""
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


def get_required_packages(init_cfg: dict, preseed_str: str) -> List[str]:
    """identify required packages for install"""
    packages = []
    # binary for pool creation must be available for the requested backend:
    # zfs, lvcreate, mkfs.btrfs
    storage_drivers: List[str] = []
    preseed_cfg: dict = {}
    if "storage_backend" in init_cfg:
        storage_drivers.append(init_cfg["storage_backend"])
    if preseed_str and "storage_pools" in preseed_str:
        # Assume correct YAML preseed format
        try:
            preseed_cfg = yaml.safe_load(preseed_str)
        except (yaml.YAMLError, TypeError, ValueError):
            LOG.warning(
                "lxd.preseed string value is not YAML. "
                " Unable to determine required storage driver packages to"
                " support storage_pools config."
            )
    for storage_pool in preseed_cfg.get("storage_pools", []):
        if storage_pool.get("driver"):
            storage_drivers.append(storage_pool["driver"])
    if "zfs" in storage_drivers and not subp.which("zfs"):
        packages.append("zfsutils-linux")
    if "lvm" in storage_drivers and not subp.which("lvcreate"):
        packages.append("lvm2")
    if "btrfs" in storage_drivers and not subp.which("mkfs.btrfs"):
        packages.append("btrfs-progs")
    return packages
