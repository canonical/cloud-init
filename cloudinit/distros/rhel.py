# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os

from cloudinit import distros, helpers, subp, util
from cloudinit.distros import PackageList, rhel_util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    # See: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Networking_Guide/sec-Network_Configuration_Using_sysconfig_Files.html # noqa
    clock_conf_fn = "/etc/sysconfig/clock"
    locale_conf_fn = "/etc/sysconfig/i18n"
    systemd_locale_conf_fn = "/etc/locale.conf"
    network_conf_fn = "/etc/sysconfig/network"
    hostname_conf_fn = "/etc/sysconfig/network"
    systemd_hostname_conf_fn = "/etc/hostname"
    tz_local_fn = "/etc/localtime"
    usr_lib_exec = "/usr/libexec"
    # RHEL and derivatives use NetworkManager DHCP client by default.
    # But if NM is configured with using dhclient ("dhcp=dhclient" statement)
    # then the following location is used:
    # /var/lib/NetworkManager/dhclient-<uuid>-<network_interface>.lease
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

    # Should be fqdn if we can use it
    # See: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/5/html/deployment_guide/ch-sysconfig  # noqa: E501
    prefer_fqdn = True

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "redhat"
        self.default_locale = "en_US.UTF-8"
        self.system_locale = None
        cfg["ssh_svcname"] = "sshd"

    def install_packages(self, pkglist: PackageList):
        self.package_command("install", pkgs=pkglist)

    def get_locale(self):
        """Return the default locale if set, else use system locale"""

        # read system locale value
        if not self.system_locale:
            self.system_locale = self._read_system_locale()

        # Return system_locale setting if valid, else use default locale
        return (
            self.system_locale if self.system_locale else self.default_locale
        )

    def apply_locale(self, locale, out_fn=None):
        if self.uses_systemd():
            if not out_fn:
                out_fn = self.systemd_locale_conf_fn
        else:
            if not out_fn:
                out_fn = self.locale_conf_fn
        locale_cfg = {
            "LANG": locale,
        }
        rhel_util.update_sysconfig_file(out_fn, locale_cfg)

    def _read_system_locale(self, keyname="LANG"):
        """Read system default locale setting, if present"""
        if self.uses_systemd():
            locale_fn = self.systemd_locale_conf_fn
        else:
            locale_fn = self.locale_conf_fn

        if not locale_fn:
            raise ValueError("Invalid path: %s" % locale_fn)

        if os.path.exists(locale_fn):
            (_exists, contents) = rhel_util.read_sysconfig_file(locale_fn)
            if keyname in contents:
                return contents[keyname]
            else:
                return None

    def _write_hostname(self, hostname, filename):
        # systemd will never update previous-hostname for us, so
        # we need to do it ourselves
        if self.uses_systemd() and filename.endswith("/previous-hostname"):
            conf = HostnameConf("")
            conf.set_hostname(hostname)
            util.write_file(filename, str(conf), 0o644)
        elif self.uses_systemd():
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
                LOG.info(
                    "create_hostname_file is False; hostname set transiently"
                )
        else:
            host_cfg = {
                "HOSTNAME": hostname,
            }
            rhel_util.update_sysconfig_file(filename, host_cfg)

    def _read_system_hostname(self):
        if self.uses_systemd():
            host_fn = self.systemd_hostname_conf_fn
        else:
            host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

    def _read_hostname(self, filename, default=None):
        if self.uses_systemd() and filename.endswith("/previous-hostname"):
            return util.load_text_file(filename).strip()
        elif self.uses_systemd():
            (out, _err) = subp.subp(["hostname"])
            out = out.strip()
            if len(out):
                return out
            else:
                return default
        else:
            (_exists, contents) = rhel_util.read_sysconfig_file(filename)
            if "HOSTNAME" in contents:
                return contents["HOSTNAME"]
            else:
                return default

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
                "ZONE": str(tz),
            }
            rhel_util.update_sysconfig_file(self.clock_conf_fn, clock_cfg)
            # This ensures that the correct tz will be used for the system
            util.copy(tz_file, self.tz_local_fn)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        if subp.which("dnf"):
            LOG.debug("Using DNF for package management")
            cmd = ["dnf"]
        else:
            LOG.debug("Using YUM for package management")
            # the '-t' argument makes yum tolerant of errors on the command
            # line with regard to packages.
            #
            # For example: if you request to install foo, bar and baz and baz
            # is installed; yum won't error out complaining that baz is already
            # installed.
            cmd = ["yum", "-t"]
        # Determines whether or not yum prompts for confirmation
        # of critical actions. We don't want to prompt...
        cmd.append("-y")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        cmd.append(command)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["makecache"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )
