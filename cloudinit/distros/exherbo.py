# Copyright (C) 2025 Clever Cloud
#
# Author: Alexandre Burgoni <alexandre.burgoni@clevercloud.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
from typing import List

from cloudinit import distros, helpers, util
from cloudinit.distros.package_management.package_manager import PackageManager
from cloudinit.distros.package_management.paludis import Paludis
from cloudinit.distros.parsers.hostname import HostnameConf

LOG = logging.getLogger(__name__)

LOCALE_SET_FILE = "/etc/env.d/99locale"

DEFAULT_LOCALE = "en_US.UTF-8"


class Distro(distros.Distro):
    init_cmd = ["systemctl"]

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "exherbo"
        if not distros.uses_systemd():
            LOG.error(
                "Cloud-init does not support non-systemd distros on Exherbo"
            )

        self.paludis = Paludis.from_config(self._runner, cfg)
        self.package_managers: List[PackageManager] = [self.paludis]

    def apply_locale(self, locale, out_fn=None):
        """Apply specified locale to system, regenerate if specified locale
        differs from system default."""
        if locale == DEFAULT_LOCALE:
            return

        util.write_file(LOCALE_SET_FILE, "LANG=%s" % locale)

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
        util.write_file(filename, str(conf), 0o644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return self.hostname_conf_fn, sys_hostname

    @staticmethod
    def _read_hostname_conf(filename):
        conf = HostnameConf(util.load_text_file(filename))
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

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if command != "upgrade":
            raise RuntimeError(f"Command {command} cannot be run")
        self.paludis.run_package_command(command, "upgrade")

    def update_package_sources(self, *, force=False):
        self.paludis.update_package_sources(force=force)
