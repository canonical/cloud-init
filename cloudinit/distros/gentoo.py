# Copyright (C) 2014 Rackspace, US Inc.
# Copyright (C) 2016 Matthew Thode.
#
# Author: Nate House <nathan.house@rackspace.com>
# Author: Matthew Thode <prometheanfire@gentoo.org>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    locale_gen_fn = "/etc/locale.gen"
    hostname_conf_fn = "/etc/conf.d/hostname"
    default_locale = "en_US.UTF-8"

    # C.UTF8 makes sense to generate, but is not selected
    # Add /etc/locale.gen entries to this list to support more locales
    locales = ["C.UTF8 UTF-8", "en_US.UTF-8 UTF-8"]

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "gentoo"
        # Fix sshd restarts
        cfg["ssh_svcname"] = "/etc/init.d/sshd"
        if distros.uses_systemd():
            LOG.error("Cloud-init does not support systemd with gentoo")

    def apply_locale(self, _, out_fn=None):
        """rc-only - not compatible with systemd

        Locales need to be added to /etc/locale.gen and generated prior
        to selection. Default to en_US.UTF-8 for simplicity.
        """
        util.write_file(self.locale_gen_fn, "\n".join(self.locales), mode=644)

        # generate locales
        subp.subp(["locale-gen"], capture=False)

        # select locale
        subp.subp(
            ["eselect", "locale", "set", self.default_locale], capture=False
        )

    def install_packages(self, pkglist: PackageList):
        self.update_package_sources()
        self.package_command("", pkgs=pkglist)

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

        # Many distro's format is the hostname by itself, and that is the
        # way HostnameConf works but gentoo expects it to be in
        #     hostname="the-actual-hostname"
        conf.set_hostname('hostname="%s"' % hostname)
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
        cmd = ["emerge"]
        # Redirect output
        cmd.append("--quiet")

        if command == "upgrade":
            cmd.extend(["--update", "world"])
        else:
            if pkgs is None:
                pkgs = []

            if args and isinstance(args, str):
                cmd.append(args)
            elif args and isinstance(args, list):
                cmd.extend(args)

            if command:
                cmd.append(command)

            pkglist = util.expand_package_list("%s-%s", pkgs)
            cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["--sync"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )
