# Copyright (C) 2021 VMware Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import distros, helpers, net, subp, util
from cloudinit.distros import PackageList
from cloudinit.distros import rhel_util as rhutil
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    systemd_hostname_conf_fn = "/etc/hostname"
    network_conf_dir = "/etc/systemd/network/"
    systemd_locale_conf_fn = "/etc/locale.conf"
    resolve_conf_fn = "/etc/systemd/resolved.conf"

    renderer_configs = {
        "networkd": {
            "resolv_conf_fn": resolve_conf_fn,
            "network_conf_dir": network_conf_dir,
        }
    }

    # Should be fqdn if we can use it
    prefer_fqdn = True

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "photon"
        self.init_cmd = ["systemctl"]

    def exec_cmd(self, cmd, capture=True):
        LOG.debug("Attempting to run: %s", cmd)
        try:
            (out, err) = subp.subp(cmd, capture=capture)
            if err:
                LOG.warning(
                    "Running %s resulted in stderr output: %s", cmd, err
                )
                return True, out, err
            return False, out, err
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Command %s failed", cmd)
            return True, None, None

    def generate_fallback_config(self):
        key = "disable_fallback_netcfg"
        disable_fallback_netcfg = self._cfg.get(key, True)
        LOG.debug("%s value is: %s", key, disable_fallback_netcfg)

        if not disable_fallback_netcfg:
            return net.generate_fallback_config()

        LOG.info(
            "Skipping generate_fallback_config. Rely on PhotonOS default "
            "network config"
        )
        return None

    def apply_locale(self, locale, out_fn=None):
        # This has a dependency on glibc-i18n, user need to manually install it
        # and enable the option in cloud.cfg
        if not out_fn:
            out_fn = self.systemd_locale_conf_fn

        locale_cfg = {
            "LANG": locale,
        }

        rhutil.update_sysconfig_file(out_fn, locale_cfg)

        # rhutil will modify /etc/locale.conf
        # For locale change to take effect, reboot is needed or we can restart
        # systemd-localed. This is equivalent of localectl
        cmd = ["systemctl", "restart", "systemd-localed"]
        self.exec_cmd(cmd)

    def install_packages(self, pkglist: PackageList):
        # self.update_package_sources()
        self.package_command("install", pkgs=pkglist)

    def _write_hostname(self, hostname, filename):
        if filename and filename.endswith("/previous-hostname"):
            util.write_file(filename, hostname)
        else:
            ret = None
            create_hostname_file = util.get_cfg_option_bool(
                self._cfg, "create_hostname_file", True
            )
            if create_hostname_file:
                ret, _out, err = self.exec_cmd(
                    ["hostnamectl", "set-hostname", str(hostname)]
                )
            else:
                ret, _out, err = self.exec_cmd(
                    [
                        "hostnamectl",
                        "set-hostname",
                        "--transient",
                        str(hostname),
                    ]
                )
                LOG.info(
                    "create_hostname_file is False; hostname set transiently"
                )
            if ret:
                LOG.warning(
                    (
                        "Error while setting hostname: %s\nGiven hostname: %s",
                        err,
                        hostname,
                    )
                )

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.systemd_hostname_conf_fn)
        return (self.systemd_hostname_conf_fn, sys_hostname)

    def _read_hostname(self, filename, default=None):
        if filename and filename.endswith("/previous-hostname"):
            return util.load_text_file(filename).strip()

        _ret, out, _err = self.exec_cmd(["hostname", "-f"])
        return out.strip() if out else default

    def _get_localhost_ip(self):
        return "127.0.1.1"

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if not pkgs:
            pkgs = []

        cmd = ["tdnf", "-y"]
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        cmd.append(command)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        ret, _out, err = self.exec_cmd(cmd)
        if ret:
            LOG.error("Error while installing packages: %s", err)

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["makecache"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )
