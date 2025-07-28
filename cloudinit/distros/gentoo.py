# Copyright (C) 2014 Rackspace, US Inc.
# Copyright (C) 2016 Matthew Thode.
# Copyright (C) 2024 Andreas K. Huettel
#
# Author: Nate House <nathan.house@rackspace.com>
# Author: Matthew Thode <prometheanfire@gentoo.org>
# Author: Andreas K. Huettel <dilfridge@gentoo.org>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource. Changes
# to it will not persist across an instance reboot. To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}

"""


class Distro(distros.Distro):
    locale_gen_fn = "/etc/locale.gen"
    default_locale = "en_US.UTF-8"
    renderer_configs = {"netifrc": {"netifrc_header": NETWORK_FILE_HEADER}}

    # C.UTF8 makes sense to generate, but is not selected
    # Add /etc/locale.gen entries to this list to support more locales
    locales = ["C.UTF8 UTF-8", "en_US.UTF-8 UTF-8"]

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)

        if distros.uses_systemd():
            self.hostname_conf_fn = "/etc/hostname"
        else:
            self.hostname_conf_fn = "/etc/conf.d/hostname"

        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "gentoo"

    def apply_locale(self, _, out_fn=None):
        """Locales need to be added to /etc/locale.gen and generated prior
        to selection. Default to en_US.UTF-8 for simplicity.
        """
        util.write_file(self.locale_gen_fn, "\n".join(self.locales), mode=644)

        # generate locales
        subp.subp(["locale-gen"], capture=False)

        # select locale, works for both openrc and systemd
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

        if distros.uses_systemd():
            # Gentoo uses the same format for /etc/hostname as everyone else-
            # only the hostname by itself. Works for openrc and systemd, but
            # openrc has its own config file and /etc/hostname is generated.
            conf.set_hostname(hostname)
        else:
            # Openrc generates /etc/hostname from /etc/conf.d/hostname with the
            # differing format
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
