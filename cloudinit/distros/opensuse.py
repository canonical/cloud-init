#    Copyright (C) 2017 SUSE LLC
#    Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Robert Schweikert <rjschwei@suse.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    Leaning very heavily on the RHEL and Debian implementation
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
from typing import Optional

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import rhel_util as rhutil
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.net import ipv4_mask_to_net_prefix
from cloudinit.net.renderer import Renderer
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    clock_conf_fn = "/etc/sysconfig/clock"
    hostname_conf_fn = "/etc/HOSTNAME"
    init_cmd = ["service"]
    locale_conf_fn = "/etc/sysconfig/language"
    network_conf_fn = "/etc/sysconfig/network/config"
    network_script_tpl = "/etc/sysconfig/network/ifcfg-%s"
    route_conf_tpl = "/etc/sysconfig/network/ifroute-%s"
    systemd_hostname_conf_fn = "/etc/hostname"
    systemd_locale_conf_fn = "/etc/locale.conf"
    tz_local_fn = "/etc/localtime"
    renderer_configs = {
        "sysconfig": {
            "control": "etc/sysconfig/network/config",
            "flavor": "suse",
            "iface_templates": "%(base)s/network/ifcfg-%(name)s",
            "netrules_path": (
                "etc/udev/rules.d/85-persistent-net-cloud-init.rules"
            ),
            "route_templates": {
                "ipv4": "%(base)s/network/ifroute-%(name)s",
                "ipv6": "%(base)s/network/ifroute-%(name)s",
            },
        }
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        self._runner = helpers.Runners(paths)
        self.osfamily = "suse"
        self.update_method = None
        self.read_only_root = False
        cfg["ssh_svcname"] = "sshd"
        if self.uses_systemd():
            self.init_cmd = ["systemctl"]
            cfg["ssh_svcname"] = "sshd.service"

    def apply_locale(self, locale, out_fn=None):
        if self.uses_systemd():
            if not out_fn:
                out_fn = self.systemd_locale_conf_fn
            locale_cfg = {"LANG": locale}
        else:
            if not out_fn:
                out_fn = self.locale_conf_fn
            locale_cfg = {"RC_LANG": locale}
        rhutil.update_sysconfig_file(out_fn, locale_cfg)

    def install_packages(self, pkglist):
        self.package_command(
            "install", args="--auto-agree-with-licenses", pkgs=pkglist
        )

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        self._set_update_method()
        if self.read_only_root and not self.update_method == "transactional":
            LOG.error(
                "Package operation requested but read only root "
                "without btrfs and transactional-updata"
            )
            return

        # No user interaction possible, enable non-interactive mode
        if self.update_method == "zypper":
            cmd = ["zypper", "--non-interactive"]
        else:
            cmd = [
                "transactional-update",
                "--non-interactive",
                "--drop-if-no-change",
                "pkg",
            ]

        # Command is the operation, such as install
        if command == "upgrade":
            command = "update"
        if (
            not pkgs
            and self.update_method == "transactional"
            and command == "update"
        ):
            command = "up"
            cmd = [
                "transactional-update",
                "--non-interactive",
                "--drop-if-no-change",
            ]
        # Repo refresh only modifies data in the read-write path,
        # always uses zypper
        if command == "refresh":
            # Repo refresh is a zypper only option, ignore the t-u setting
            cmd = ["zypper", "--non-interactive"]
        cmd.append(command)

        # args are the arguments to the command, not global options
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

        if self.update_method == "transactional":
            LOG.info(
                "To use/activate the installed packages reboot the system"
            )

    def set_timezone(self, tz):
        tz_file = self._find_tz_file(tz)
        if self.uses_systemd():
            # Currently, timedatectl complains if invoked during startup
            # so for compatibility, create the link manually.
            util.del_file(self.tz_local_fn)
            util.sym_link(tz_file, self.tz_local_fn)
        else:
            # Adjust the sysconfig clock zone setting
            clock_cfg = {
                "TIMEZONE": str(tz),
            }
            rhutil.update_sysconfig_file(self.clock_conf_fn, clock_cfg)
            # This ensures that the correct tz will be used for the system
            util.copy(tz_file, self.tz_local_fn)

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["refresh"],
            freq=PER_INSTANCE,
        )

    def _read_hostname(self, filename, default=None):
        if self.uses_systemd() and filename.endswith("/previous-hostname"):
            return util.load_file(filename).strip()
        elif self.uses_systemd():
            (out, _err) = subp.subp(["hostname"])
            if len(out):
                return out
            else:
                return default
        else:
            try:
                conf = self._read_hostname_conf(filename)
                hostname = conf.hostname
            except IOError:
                pass
            if not hostname:
                return default
            return hostname

    def _get_localhost_ip(self):
        return "127.0.1.1"

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_file(filename))
        conf.parse()
        return conf

    def _read_system_hostname(self):
        if self.uses_systemd():
            host_fn = self.systemd_hostname_conf_fn
        else:
            host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

    def _set_update_method(self):
        """Decide if we want to use transactional-update or zypper"""
        if self.update_method is None:
            result = util.get_mount_info("/")
            fs_type = ""
            if result:
                (devpth, fs_type, mount_point) = result
                # Check if the file system is read only
                mounts = util.load_file("/proc/mounts").split("\n")
                for mount in mounts:
                    if mount.startswith(devpth):
                        mount_info = mount.split()
                        if mount_info[1] != mount_point:
                            continue
                        self.read_only_root = mount_info[3].startswith("ro")
                        break
                if fs_type.lower() == "btrfs" and os.path.exists(
                    "/usr/sbin/transactional-update"
                ):
                    self.update_method = "transactional"
                else:
                    self.update_method = "zypper"
            else:
                LOG.info(
                    "Could not determine filesystem type of '/' using zypper"
                )
                self.update_method = "zypper"

    def _write_hostname(self, hostname, filename):
        create_hostname_file = util.get_cfg_option_bool(
            self._cfg, "create_hostname_file", True
        )
        if self.uses_systemd() and filename.endswith("/previous-hostname"):
            util.write_file(filename, hostname)
        elif self.uses_systemd():
            if create_hostname_file:
                subp.subp(["hostnamectl", "set-hostname", str(hostname)])
            else:
                subp.subp(
                    [
                        "hostnamectl",
                        "set-hostname",
                        "--transient",
                        str(hostname),
                    ]
                )
        else:
            conf = None
            try:
                # Try to update the previous one
                # so lets see if we can read it first.
                conf = self._read_hostname_conf(filename)
            except IOError:
                if create_hostname_file:
                    pass
                else:
                    return
            if not conf:
                conf = HostnameConf("")
            conf.set_hostname(hostname)
            util.write_file(filename, str(conf), 0o644)

    @property
    def preferred_ntp_clients(self):
        """The preferred ntp client is dependent on the version."""

        # Allow distro to determine the preferred ntp client list
        if not self._preferred_ntp_clients:
            distro_info = util.system_info()["dist"]
            name = distro_info[0]
            major_ver = int(distro_info[1].split(".")[0])

            # This is horribly complicated because of a case of
            # "we do not care if versions should be increasing syndrome"
            if (major_ver >= 15 and "openSUSE" not in name) or (
                major_ver >= 15 and "openSUSE" in name and major_ver != 42
            ):
                self._preferred_ntp_clients = [
                    "chrony",
                    "systemd-timesyncd",
                    "ntp",
                ]
            else:
                self._preferred_ntp_clients = [
                    "ntp",
                    "systemd-timesyncd",
                    "chrony",
                ]

        return self._preferred_ntp_clients

    def _write_network_state(
        self,
        network_state,
        renderer: Renderer,
        netconfig: Optional[dict] = None,
    ):
        super()._write_network_state(network_state, renderer)
        netconfig = netconfig or {}
        netconfig_ver = netconfig.get("version")
        if netconfig_ver == 1:
            self._write_routes_v1(netconfig)
        elif netconfig_ver == 2:
            self._write_routes_v2(netconfig)
        else:
            LOG.warning(
                "unsupported or missing netconfig version, not writing routes"
            )

    def _write_routes_v1(self, netconfig: dict):
        """Write route files, not part of the standard distro interface"""
        # Due to the implementation of the sysconfig renderer default routes
        # are setup in ifcfg-* files. But this does not work on SLES or
        # openSUSE https://bugs.launchpad.net/cloud-init/+bug/1812117
        # this is a very hacky way to get around the problem until a real
        # solution is found in the sysconfig renderer
        device_configs = netconfig.get("config", [])
        default_nets = ("::", "0.0.0.0")
        for config in device_configs:
            if_name = config.get("name")
            subnets = config.get("subnets", [])
            config_routes = ""
            has_default_route = False
            seen_default_gateway = None
            for subnet in subnets:
                # Render the default gateway if it is present
                gateway = subnet.get("gateway")
                if gateway:
                    config_routes += " ".join(["default", gateway, "-", "-\n"])
                    has_default_route = True
                    if not seen_default_gateway:
                        seen_default_gateway = gateway
                # Render subnet routes
                routes = subnet.get("routes", [])
                for route in routes:
                    dest = route.get("destination") or route.get("network")
                    if not dest or dest in default_nets:
                        dest = "default"
                        if not has_default_route:
                            has_default_route = True
                    if dest != "default":
                        netmask = route.get("netmask")
                        if netmask:
                            prefix = ipv4_mask_to_net_prefix(netmask)
                            dest += "/" + str(prefix)
                        if "/" not in dest:
                            LOG.warning(
                                'Skipping route; has no prefix "%s"', dest
                            )
                            continue
                    gateway = route.get("gateway")
                    if not gateway:
                        LOG.warning('Missing gateway for "%s", skipping', dest)
                        continue
                    if (
                        dest == "default"
                        and has_default_route
                        and gateway == seen_default_gateway
                    ):
                        dest_info = dest
                        if gateway:
                            dest_info = " ".join([dest, gateway, "-", "-"])
                        LOG.warning(
                            '%s already has default route, skipping "%s"',
                            if_name,
                            dest_info,
                        )
                        continue
                    config_routes += " ".join([dest, gateway, "-", "-\n"])
            if config_routes:
                route_file = f"/etc/sysconfig/network/ifroute-{if_name}"
                util.write_file(route_file, config_routes)

    def _render_route_string(self, netconfig_route: dict):
        route_to = netconfig_route.get("to", None)
        route_via = netconfig_route.get("via", None)
        route_metric = netconfig_route.get("metric", None)
        route_string = ""

        if route_to and route_via:
            route_string = " ".join([route_to, route_via, "-", "-"])
            if route_metric:
                route_string += " metric {}\n".format(route_metric)
            else:
                route_string += "\n"
        else:
            LOG.warning("invalid route definition, skipping route")

        return route_string

    def _write_routes_v2(self, netconfig: dict):
        for device_type in netconfig:
            if device_type == "version":
                continue

            if device_type == "routes":
                # global static routes
                config_routes = ""
                for route in netconfig["routes"]:
                    config_routes += self._render_route_string(route)
                if config_routes:
                    route_file = "/etc/sysconfig/network/routes"
                    util.write_file(route_file, config_routes)
            else:
                devices = netconfig[device_type]
                for device_name in devices:
                    config_routes = ""
                    device_config = devices[device_name]
                    try:
                        gateways = [
                            v
                            for k, v in device_config.items()
                            if "gateway" in k
                        ]
                        for gateway in gateways:
                            config_routes += " ".join(
                                ["default", gateway, "-", "-\n"]
                            )
                        for route in device_config.get("routes", []):
                            config_routes += self._render_route_string(route)
                        if config_routes:
                            route_file = (
                                "/etc/sysconfig/network/ifroute-{}".format(
                                    device_name
                                )
                            )
                            util.write_file(route_file, config_routes)
                    except Exception:
                        # the parser above expects another level of nesting
                        # which should be there in case it's properly
                        # formatted; if not we may get an exception on items()
                        pass
