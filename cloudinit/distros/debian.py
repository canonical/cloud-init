# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
from typing import List

from cloudinit import distros, subp, util
from cloudinit.distros.package_management.apt import Apt
from cloudinit.distros.package_management.package_manager import PackageManager
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.net.netplan import CLOUDINIT_NETPLAN_FILE

LOG = logging.getLogger(__name__)

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
"""

LOCALE_CONF_FN = "/etc/default/locale"


class Distro(distros.Distro):
    hostname_conf_fn = "/etc/hostname"
    network_conf_fn = {
        "eni": "/etc/network/interfaces.d/50-cloud-init",
        "netplan": CLOUDINIT_NETPLAN_FILE,
    }
    renderer_configs = {
        "eni": {
            "eni_path": network_conf_fn["eni"],
            "eni_header": NETWORK_FILE_HEADER,
        },
        "netplan": {
            "netplan_path": network_conf_fn["netplan"],
            "netplan_header": NETWORK_FILE_HEADER,
            "postcmds": True,
        },
    }
    # Debian stores dhclient leases at following location:
    # /var/lib/dhcp/dhclient.<iface_name>.leases
    dhclient_lease_directory = "/var/lib/dhcp"
    dhclient_lease_file_regex = r"dhclient\.\w+\.leases"

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self.osfamily = "debian"
        self.default_locale = "C.UTF-8"
        self.system_locale = None
        self.apt = Apt.from_config(self._runner, cfg)
        self.package_managers: List[PackageManager] = [self.apt]

    def get_locale(self):
        """Return the default locale if set, else use default locale"""
        # read system locale value
        if not self.system_locale:
            self.system_locale = read_system_locale()

        # Return system_locale setting if valid, else use default locale
        return (
            self.system_locale if self.system_locale else self.default_locale
        )

    def apply_locale(self, locale, out_fn=None, keyname="LANG"):
        """Apply specified locale to system, regenerate if specified locale
        differs from system default."""
        if not out_fn:
            out_fn = LOCALE_CONF_FN

        if not locale:
            raise ValueError("Failed to provide locale value.")

        # Only call locale regeneration if needed
        # Update system locale config with specified locale if needed
        distro_locale = self.get_locale()
        conf_fn_exists = os.path.exists(out_fn)
        sys_locale_unset = not self.system_locale
        if sys_locale_unset:
            LOG.debug(
                "System locale not found in %s. "
                "Assuming system locale is %s based on hardcoded default",
                LOCALE_CONF_FN,
                self.default_locale,
            )
        else:
            LOG.debug(
                "System locale set to %s via %s",
                self.system_locale,
                LOCALE_CONF_FN,
            )
        need_regen = (
            locale.lower() != distro_locale.lower()
            or not conf_fn_exists
            or sys_locale_unset
        )
        need_conf = not conf_fn_exists or need_regen or sys_locale_unset

        if need_regen:
            regenerate_locale(locale, out_fn, keyname=keyname)
        else:
            LOG.debug(
                "System has '%s=%s' requested '%s', skipping regeneration.",
                keyname,
                self.system_locale,
                locale,
            )

        if need_conf:
            update_locale_conf(locale, out_fn, keyname=keyname)
            # once we've updated the system config, invalidate cache
            self.system_locale = None

    def _write_network_state(self, *args, **kwargs):
        _maybe_remove_legacy_eth0()
        return super()._write_network_state(*args, **kwargs)

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
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname_conf(self, filename):
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

    def _get_localhost_ip(self):
        # Note: http://www.leonardoborda.com/blog/127-0-1-1-ubuntu-debian/
        return "127.0.1.1"

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        # As of this writing, the only use of `package_command` outside of
        # distros calling it within their own classes is calling "upgrade"
        if command != "upgrade":
            raise RuntimeError(f"Unable to handle {command} command")
        self.apt.run_package_command("upgrade")

    def get_primary_arch(self):
        return util.get_dpkg_architecture()

    def set_keymap(self, layout: str, model: str, variant: str, options: str):
        # localectl is broken on some versions of Debian. See
        # https://bugs.launchpad.net/ubuntu/+source/systemd/+bug/2030788 and
        # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1038762
        #
        # Instead, write the file directly. According to the keyboard(5) man
        # page, this file is shared between both X and the console.

        contents = "\n".join(
            [
                "# This file was generated by cloud-init",
                "",
                f'XKBMODEL="{model}"',
                f'XKBLAYOUT="{layout}"',
                f'XKBVARIANT="{variant}"',
                f'XKBOPTIONS="{options}"',
                "",
                'BACKSPACE="guess"',  # This is provided on default installs
                "",
            ]
        )
        util.write_file(
            filename="/etc/default/keyboard",
            content=contents,
            mode=0o644,
            omode="w",
        )

        # Due to
        # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=926037
        # if localectl can be used in the future, this line may still
        # be needed
        self.manage_service("restart", "console-setup")


def _maybe_remove_legacy_eth0(path="/etc/network/interfaces.d/eth0.cfg"):
    """Ubuntu cloud images previously included a 'eth0.cfg' that had
    hard coded content.  That file would interfere with the rendered
    configuration if it was present.

    if the file does not exist do nothing.
    If the file exists:
      - with known content, remove it and warn
      - with unknown content, leave it and warn
    """

    if not os.path.exists(path):
        return

    bmsg = "Dynamic networking config may not apply."
    try:
        contents = util.load_text_file(path)
        known_contents = ["auto eth0", "iface eth0 inet dhcp"]
        lines = [
            f.strip() for f in contents.splitlines() if not f.startswith("#")
        ]
        if lines == known_contents:
            util.del_file(path)
            msg = "removed %s with known contents" % path
        else:
            msg = bmsg + " '%s' exists with user configured content." % path
    except Exception:
        msg = bmsg + " %s exists, but could not be read." % path

    LOG.warning(msg)


def read_system_locale(sys_path=LOCALE_CONF_FN, keyname="LANG"):
    """Read system default locale setting, if present"""
    sys_val = ""
    if not sys_path:
        raise ValueError("Invalid path: %s" % sys_path)

    if os.path.exists(sys_path):
        locale_content = util.load_text_file(sys_path)
        sys_defaults = util.load_shell_content(locale_content)
        sys_val = sys_defaults.get(keyname, "")

    return sys_val


def update_locale_conf(locale, sys_path, keyname="LANG"):
    """Update system locale config"""
    LOG.debug(
        "Updating %s with locale setting %s=%s", sys_path, keyname, locale
    )
    subp.subp(
        [
            "update-locale",
            "--locale-file=" + sys_path,
            "%s=%s" % (keyname, locale),
        ],
        capture=False,
    )


def regenerate_locale(locale, sys_path, keyname="LANG"):
    """
    Run locale-gen for the provided locale and set the default
    system variable `keyname` appropriately in the provided `sys_path`.

    """
    # special case for locales which do not require regen
    # % locale -a
    # C
    # C.UTF-8
    # POSIX
    if locale.lower() in ["c", "c.utf-8", "posix"]:
        LOG.debug("%s=%s does not require rengeneration", keyname, locale)
        return

    # finally, trigger regeneration
    LOG.debug("Generating locales for %s", locale)
    subp.subp(["locale-gen", locale], capture=False)
