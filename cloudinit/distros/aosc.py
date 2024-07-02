# Copyright (C) 2024 AOSC Developers
#
# Author: Yuanhang Sun <leavelet@aosc.io>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList, rhel_util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    systemd_locale_conf_fn = "/etc/locale.conf"
    init_cmd = ["systemctl"]
    network_conf_dir = "/etc/systemd/network/"
    resolve_conf_fn = "/etc/systemd/resolved.conf"
    tz_local_fn = "/etc/localtime"

    renderer_configs = {
        "networkd": {
            "resolv_conf_fn": resolve_conf_fn,
            "network_conf_dir": network_conf_dir,
        },
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        self._runner = helpers.Runners(paths)
        self.osfamily = "aosc"
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

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            "refresh",
            freq=PER_INSTANCE,
        )
