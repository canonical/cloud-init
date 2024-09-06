# Copyright (C) 2024 AOSC Developers
#
# Author: Yuanhang Sun <leavelet@aosc.io>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.distros.parsers.sys_conf import SysConf
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    systemd_locale_conf_fn = "/etc/locale.conf"
    init_cmd = ["systemctl"]
    network_conf_dir = "/etc/sysconfig/network"
    resolve_conf_fn = "/etc/systemd/resolved.conf"
    tz_local_fn = "/etc/localtime"

    dhclient_lease_directory = "/var/lib/NetworkManager"
    dhclient_lease_file_regex = r"dhclient-[\w-]+\.lease"

    renderer_configs = {
        "sysconfig": {
            "control": "etc/sysconfig/network",
            "iface_templates": "%(base)s/network-scripts/ifcfg-%(name)s",
            "route_templates": {
                "ipv4": "%(base)s/network-scripts/route-%(name)s",
                "ipv6": "%(base)s/network-scripts/route6-%(name)s",
            },
        }
    }

    prefer_fqdn = False

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        self._runner = helpers.Runners(paths)
        self.osfamily = "aosc"
        self.default_locale = "en_US.UTF-8"
        cfg["ssh_svcname"] = "sshd"

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self.systemd_locale_conf_fn
        locale_cfg = {
            "LANG": locale,
        }
        update_locale_conf(out_fn, locale_cfg)

    def _write_hostname(self, hostname, filename):
        if filename.endswith("/previous-hostname"):
            conf = HostnameConf("")
            conf.set_hostname(hostname)
            util.write_file(filename, str(conf), 0o644)
        create_hostname_file = util.get_cfg_option_bool(
            self._cfg, "create_hostname_file", True
        )
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
            LOG.info("create_hostname_file is False; hostname set transiently")

    def _read_hostname(self, filename, default=None):
        if filename.endswith("/previous-hostname"):
            return util.load_text_file(filename).strip()
        (out, _err) = subp.subp(["hostname"])
        out = out.strip()
        if len(out):
            return out
        else:
            return default

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def set_timezone(self, tz):
        tz_file = self._find_tz_file(tz)
        util.del_file(self.tz_local_fn)
        util.sym_link(tz_file, self.tz_local_fn)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ["oma"]
        if command:
            cmd.append(command)
        cmd.append("-y")
        cmd.extend(pkgs)

        subp.subp(cmd, capture=False)

    def install_packages(self, pkglist: PackageList):
        self.package_command("install", pkgs=pkglist)

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            "refresh",
            freq=PER_INSTANCE,
        )


def read_locale_conf(sys_path):
    exists = False
    try:
        contents = util.load_text_file(sys_path).splitlines()
        exists = True
    except IOError:
        contents = []
    return (exists, SysConf(contents))


def update_locale_conf(sys_path, locale_cfg):
    if not locale_cfg:
        return
    (exists, contents) = read_locale_conf(sys_path)
    updated_am = 0
    for k, v in locale_cfg.items():
        if v is None:
            continue
        v = str(v)
        if len(v) == 0:
            continue
        contents[k] = v
        updated_am += 1
    if updated_am:
        lines = [
            str(contents),
        ]
        if not exists:
            lines.insert(0, util.make_header())
        util.write_file(sys_path, "\n".join(lines) + "\n", 0o644)
