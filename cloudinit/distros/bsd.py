import logging
import platform
import re
from typing import List, Optional

import cloudinit.net.netops.bsd_netops as bsd_netops
from cloudinit import distros, helpers, net, subp, util
from cloudinit.distros import PackageList, bsd_utils
from cloudinit.distros.networking import BSDNetworking

LOG = logging.getLogger(__name__)


class BSD(distros.Distro):
    networking_cls = BSDNetworking
    hostname_conf_fn = "/etc/rc.conf"
    rc_conf_fn = "/etc/rc.conf"
    default_owner = "root:wheel"

    # This differs from the parent Distro class, which has -P for
    # poweroff.
    shutdown_options_map = {"halt": "-H", "poweroff": "-p", "reboot": "-r"}

    # Set in BSD distro subclasses
    group_add_cmd_prefix: List[str] = []
    pkg_cmd_install_prefix: List[str] = []
    pkg_cmd_remove_prefix: List[str] = []
    # There is no update/upgrade on OpenBSD
    pkg_cmd_update_prefix: Optional[List[str]] = None
    pkg_cmd_upgrade_prefix: Optional[List[str]] = None
    net_ops = bsd_netops.BsdNetOps

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        cfg["ssh_svcname"] = "sshd"
        cfg["rsyslog_svcname"] = "rsyslogd"
        self.osfamily = platform.system().lower()
        self.net_ops = bsd_netops.BsdNetOps

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname(self, filename, default=None):
        return bsd_utils.get_rc_config_value("hostname")

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        raise NotImplementedError("Return list cmd to add member to group")

    def _write_hostname(self, hostname, filename):
        bsd_utils.set_rc_config_value("hostname", hostname, fn="/etc/rc.conf")

    def create_group(self, name, members=None):
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            group_add_cmd = self.group_add_cmd_prefix + [name]
            try:
                subp.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)

        if not members:
            members = []
        for member in members:
            if not util.is_user(member):
                LOG.warning(
                    "Unable to add group member '%s' to group '%s'"
                    "; user does not exist.",
                    member,
                    name,
                )
                continue
            try:
                subp.subp(self._get_add_member_to_group_cmd(member, name))
                LOG.info("Added user '%s' to group '%s'", member, name)
            except Exception:
                util.logexc(
                    LOG, "Failed to add user '%s' to group '%s'", member, name
                )

    def generate_fallback_config(self):
        nconf = {"config": [], "version": 1}
        for mac, name in net.get_interfaces_by_mac().items():
            nconf["config"].append(
                {
                    "type": "physical",
                    "name": name,
                    "mac_address": mac,
                    "subnets": [{"type": "dhcp"}],
                }
            )
        return nconf

    def install_packages(self, pkglist: PackageList):
        self.update_package_sources()
        self.package_command("install", pkgs=pkglist)

    def _get_pkg_cmd_environ(self):
        """Return environment vars used in *BSD package_command operations"""
        raise NotImplementedError("BSD subclasses return a dict of env vars")

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        if command == "install":
            cmd = self.pkg_cmd_install_prefix
        elif command == "remove":
            cmd = self.pkg_cmd_remove_prefix
        elif command == "update":
            if not self.pkg_cmd_update_prefix:
                return
            cmd = self.pkg_cmd_update_prefix
        elif command == "upgrade":
            if not self.pkg_cmd_upgrade_prefix:
                return
            cmd = self.pkg_cmd_upgrade_prefix
        else:
            cmd = []

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, update_env=self._get_pkg_cmd_environ(), capture=False)

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def apply_locale(self, locale, out_fn=None):
        LOG.debug("Cannot set the locale.")

    def chpasswd(self, plist_in: list, hashed: bool):
        for name, password in plist_in:
            self.set_passwd(name, password, hashed=hashed)

    @staticmethod
    def get_proc_ppid(pid):
        """
        Return the parent pid of a process by checking ps
        """
        ppid, _ = subp.subp(["ps", "-oppid=", "-p", str(pid)])
        return int(ppid.strip())

    @staticmethod
    def get_mapped_device(blockdev: str) -> Optional[str]:
        return None

    @staticmethod
    def device_part_info(devpath: str) -> tuple:
        # FreeBSD doesn't know of sysfs so just get everything we need from
        # the device, like /dev/vtbd0p2.
        part = util.find_freebsd_part(devpath)
        if part:
            fpart = f"/dev/{part}"
            # Handle both GPT partitions and MBR slices with partitions
            m = re.search(
                r"^(?P<dev>/dev/.+)[sp](?P<part_slice>\d+[a-z]*)$", fpart
            )
            if m:
                return m["dev"], m["part_slice"]

        # the input is bogus and we need to bail
        raise ValueError(f"Invalid value for devpath: '{devpath}'")
