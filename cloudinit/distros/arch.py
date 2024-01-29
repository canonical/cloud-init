# Copyright (C) 2014 Rackspace, US Inc.
#
# Author: Nate House <nathan.house@rackspace.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
from typing import List

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList, net_util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.net.netplan import CLOUDINIT_NETPLAN_FILE
from cloudinit.net.renderer import Renderer
from cloudinit.net.renderers import RendererNotFoundError
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    locale_gen_fn = "/etc/locale.gen"
    network_conf_dir = "/etc/netctl"
    init_cmd = ["systemctl"]  # init scripts
    update_initramfs_cmd: List[str] = []  # TODO(define mkinicpio support)
    renderer_configs = {
        "netplan": {
            "netplan_path": CLOUDINIT_NETPLAN_FILE,
            "netplan_header": "# generated by cloud-init\n",
            "postcmds": True,
        }
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "arch"
        cfg["ssh_svcname"] = "sshd"

    def apply_locale(self, locale, out_fn=None):
        if out_fn is not None and out_fn != "/etc/locale.conf":
            LOG.warning(
                "Invalid locale_configfile %s, only supported "
                "value is /etc/locale.conf",
                out_fn,
            )
        lines = [
            util.make_header(),
            # Hard-coding the charset isn't ideal, but there is no other way.
            "%s UTF-8" % (locale),
            "",
        ]
        util.write_file(self.locale_gen_fn, "\n".join(lines))
        subp.subp(["locale-gen"], capture=False)
        # In the future systemd can handle locale-gen stuff:
        # https://github.com/systemd/systemd/pull/9864
        subp.subp(["localectl", "set-locale", locale], capture=False)

    def install_packages(self, pkglist: PackageList):
        self.update_package_sources()
        self.package_command("", pkgs=pkglist)

    def _get_renderer(self) -> Renderer:
        try:
            return super()._get_renderer()
        except RendererNotFoundError as e:
            # Fall back to old _write_network
            raise NotImplementedError from e

    def _write_network(self, settings):
        entries = net_util.translate_network(settings)
        LOG.debug(
            "Translated ubuntu style network settings %s into %s",
            settings,
            entries,
        )
        return _render_network(
            entries,
            resolv_conf=self.resolve_conf_fn,
            conf_dir=self.network_conf_dir,
            enable_func=self._enable_interface,
        )

    def _enable_interface(self, device_name):
        cmd = ["netctl", "reenable", device_name]
        try:
            (_out, err) = subp.subp(cmd)
            if len(err):
                LOG.warning(
                    "Running %s resulted in stderr output: %s", cmd, err
                )
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)

    def _bring_up_interface(self, device_name):
        cmd = ["netctl", "restart", device_name]
        LOG.debug(
            "Attempting to run bring up interface %s using command %s",
            device_name,
            cmd,
        )
        try:
            (_out, err) = subp.subp(cmd)
            if len(err):
                LOG.warning(
                    "Running %s resulted in stderr output: %s", cmd, err
                )
            return True
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _write_hostname(self, hostname, filename):
        conf = None
        try:
            # Try to update the previous one
            # so lets see if we can read it first.
            conf = self._read_hostname_conf(filename)
        except IOError:
            create_hostname_file = util.get_cfg_option_bool(
                self._cfg, "create_hostname_file", True
            )
            if create_hostname_file:
                pass
            else:
                LOG.info(
                    "create_hostname_file is False; hostname file not created"
                )
                return
        if not conf:
            conf = HostnameConf("")
        conf.set_hostname(hostname)
        util.write_file(filename, str(conf), omode="w", mode=0o644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_file(filename))
        conf.parse()
        return conf

    def _read_hostname(self, filename, default=None):
        hostname = None
        try:
            conf = self._read_hostname_conf(filename)
            hostname = conf.hostname
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    # hostname (inetutils) isn't installed per default on arch, so we use
    # hostnamectl which is installed per default (systemd).
    def _apply_hostname(self, hostname):
        LOG.debug(
            "Non-persistently setting the system hostname to %s", hostname
        )
        try:
            subp.subp(["hostnamectl", "--transient", "set-hostname", hostname])
        except subp.ProcessExecutionError:
            util.logexc(
                LOG,
                "Failed to non-persistently adjust the system hostname to %s",
                hostname,
            )

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ["pacman", "-Sy", "--quiet", "--noconfirm"]
        # Redirect output

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command == "upgrade":
            command = "-u"
        if command:
            cmd.append(command)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run(
            "update-sources", self.package_command, ["-y"], freq=PER_INSTANCE
        )


def _render_network(
    entries,
    target="/",
    conf_dir="etc/netctl",
    resolv_conf="etc/resolv.conf",
    enable_func=None,
):
    """Render the translate_network format into netctl files in target.
    Paths will be rendered under target.
    """

    devs = []
    nameservers = []
    resolv_conf = subp.target_path(target, resolv_conf)
    conf_dir = subp.target_path(target, conf_dir)

    for (dev, info) in entries.items():
        if dev == "lo":
            # no configuration should be rendered for 'lo'
            continue
        devs.append(dev)
        net_fn = os.path.join(conf_dir, dev)
        net_cfg = {
            "Connection": "ethernet",
            "Interface": dev,
            "IP": info.get("bootproto"),
            "Address": "%s/%s" % (info.get("address"), info.get("netmask")),
            "Gateway": info.get("gateway"),
            "DNS": info.get("dns-nameservers", []),
        }
        util.write_file(net_fn, convert_netctl(net_cfg))
        if enable_func and info.get("auto"):
            enable_func(dev)
        if "dns-nameservers" in info:
            nameservers.extend(info["dns-nameservers"])

    if nameservers:
        util.write_file(resolv_conf, convert_resolv_conf(nameservers))
    return devs


def convert_netctl(settings):
    """Given a dictionary, returns a string in netctl profile format.

    netctl profile is described at:
    https://git.archlinux.org/netctl.git/tree/docs/netctl.profile.5.txt

    Note that the 'Special Quoting Rules' are not handled here."""
    result = []
    for key in sorted(settings):
        val = settings[key]
        if val is None:
            val = ""
        elif isinstance(val, (tuple, list)):
            val = "(" + " ".join("'%s'" % v for v in val) + ")"
        result.append("%s=%s\n" % (key, val))
    return "".join(result)


def convert_resolv_conf(settings):
    """Returns a settings string formatted for resolv.conf."""
    result = ""
    if isinstance(settings, list):
        for ns in settings:
            result = result + "nameserver %s\n" % ns
    return result
