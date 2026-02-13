# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2025 Raspberry Pi Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import re
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
LOCALE_GEN_FN = "/etc/locale.gen"
SUPPORTED_FN = "/usr/share/i18n/SUPPORTED"


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

        # Make sure it has a charset for system commands to work
        locale = _normalize_locale(locale)

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
            regenerate_locale(
                locale,
                self.default_locale,
                keyname=keyname,
                install_function=self.install_packages,
            )
        else:
            LOG.debug(
                "System has '%s=%s' requested '%s', skipping regeneration.",
                keyname,
                self.system_locale,
                locale,
            )

        if need_conf:
            update_locale_conf(
                locale,
                out_fn,
                self.default_locale,
                keyname=keyname,
                install_function=self.install_packages,
            )
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


def _ensure_tool(bin_name: str, install_function=None, pkgs=None):
    if subp.which(bin_name):
        return
    if install_function and pkgs:
        install_function(pkgs)
    # if not present and installed raise no RuntimeError
    # but wait for subp to fail


def _normalize_locale(requested: str) -> str:
    if not requested:
        raise ValueError("Failed to provide locale value.")
    req = requested.strip()

    # Accept canonical “no-regeneration” values as-is
    if req.lower() in ("c", "posix", "c.utf-8", "c.utf8"):
        return (
            "C.UTF-8" if req.lower() != "c" and "utf" in req.lower() else "C"
        )

    # If no charset specified, default to UTF-8
    if "." not in req and "@" not in req:
        return req + ".UTF-8"
    return req


def update_locale_conf(
    locale, sys_path, default_locale, keyname="LANG", install_function=None
):
    """Update system locale config"""
    LOG.debug(
        "Updating %s with locale setting %s=%s", sys_path, keyname, locale
    )
    _ensure_tool("update-locale", install_function, ["locales"])
    subp.subp(
        [
            "update-locale",
            "--locale-file=" + sys_path,
            "%s=%s" % (keyname, locale),
        ],
        update_env={
            "LANGUAGE": default_locale,
            "LANG": default_locale,
            "LC_ALL": default_locale,
        },
        capture=False,
    )


def _lookup_supported_line(requested: str) -> str:
    """
    Return the canonical line from /usr/share/i18n/SUPPORTED for `requested`.

    Accepts:
      - bare language_region:   "fi_FI"
      - with charset:           "fi_FI.ISO-8859-1" or "fi_FI.UTF-8"
      - with modifier:          "fi_FI@euro" (works with/without charset)

    Prefers UTF-8 only when the request didn’t specify a charset and multiple
    candidates exist; otherwise returns the first match.
    """
    try:
        sup = util.load_text_file(SUPPORTED_FN).splitlines()
    except Exception:
        sup = []

    # Parse requested into locale[.charset][@mod]
    m = re.match(
        r"^([A-Za-z_]+)(?:\.([A-Za-z0-9\-]+))?(?:@([A-Za-z0-9_\-]+))?$",
        requested,
    )
    if not m:
        # fallback: treat whole string as a prefix
        prefix = requested
        wanted_charset = None
        wanted_mod = None
    else:
        base, wanted_charset, wanted_mod = m.group(1), m.group(2), m.group(3)
        prefix = base + (f"@{wanted_mod}" if wanted_mod else "")

    # Collect candidates that start with requested locale (+modifier),
    # each SUPPORTED line is "locale[.charset][@mod] <space> CHARMAP"
    candidates = []
    rx = re.compile(
        rf"^{re.escape(prefix)}(?:\.[^\s@]+)?(?:@[^\s]+)?\s+[^\s]+$"
    )
    for line in sup:
        if not line or line.startswith("#"):
            continue
        if rx.match(line):
            candidates.append(line.strip())

    if not candidates:
        # As a last resort, construct a reasonable default (don’t force UTF-8)
        # If user gave a charset, use it; else use UTF-8.
        if wanted_charset:
            constructed = f"{prefix}.{wanted_charset} {wanted_charset}"
        else:
            constructed = f"{prefix}.UTF-8 UTF-8"
        return constructed

    if wanted_charset:
        # Find exact charset match on first field (before space)
        rx_exact = re.compile(
            rf"^{re.escape(prefix)}\.{re.escape(wanted_charset)}(?:@[^\s]+)?\s+"
        )
        for line in candidates:
            if rx_exact.match(line):
                return line

    # No explicit charset requested: prefer UTF-8 if
    # present, else first candidate
    for line in candidates:
        if re.search(r"\sUTF-8$", line, re.IGNORECASE):
            return line
    return candidates[0]


def regenerate_locale(
    locale, default_locale, keyname="LANG", install_function=None
):
    """
    Ensure `locale` is enabled in /etc/locale.gen, then run locale-gen.
    Debian's locale-gen reads /etc/locale.gen and ignores positional args.
    """

    # special case for locales which do not require regen
    # % locale -a
    # C
    # C.UTF-8
    # POSIX
    if locale.lower() in ["c", "c.utf-8", "posix"]:
        LOG.debug("%s=%s does not require rengeneration", keyname, locale)
        return

    # ensure tooling
    _ensure_tool("locale-gen", install_function, ["locales"])

    # compute canonical line and NEW_LANG (first field)
    line = _lookup_supported_line(locale)

    # ensure /etc/locale.gen contains the
    # line (uncomment if present; append if absent)
    existing = ""
    if os.path.exists(LOCALE_GEN_FN):
        try:
            existing = util.load_text_file(LOCALE_GEN_FN)
        except Exception:
            existing = ""

    out_lines = []
    found_enabled = False
    target_re = re.compile(rf"^#?\s*{re.escape(line)}\s*$")

    for raw in existing.splitlines():
        s = raw.strip()
        if not s:
            out_lines.append(raw)
            continue

        if target_re.match(s.lstrip("# ").rstrip()):
            # enable target locale
            out_lines.append(line)
            found_enabled = True
        else:
            # disable everything else
            if raw.lstrip().startswith("#"):
                out_lines.append(raw)  # already commented
            else:
                out_lines.append("# " + raw)

    if not found_enabled:
        out_lines.append(line)

    util.ensure_dir(os.path.dirname(LOCALE_GEN_FN))
    util.write_file(LOCALE_GEN_FN, "\n".join(out_lines).rstrip() + "\n")

    # finally, generate locales listed in /etc/locale.gen
    LOG.debug("Generating locales for %s", locale)
    # TODO: maybe --keep-existing to avoid removing existing locales?
    subp.subp(
        ["locale-gen"],
        capture=False,
        update_env={
            "LANGUAGE": default_locale,
            "LANG": default_locale,
            "LC_ALL": default_locale,
        },
    )
