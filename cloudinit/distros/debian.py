# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import fcntl
import os
import time

from cloudinit import distros, helpers
from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

APT_LOCK_WAIT_TIMEOUT = 30
APT_GET_COMMAND = (
    "apt-get",
    "--option=Dpkg::Options::=--force-confold",
    "--option=Dpkg::options::=--force-unsafe-io",
    "--assume-yes",
    "--quiet",
)
APT_GET_WRAPPER = {
    "command": "eatmydata",
    "enabled": "auto",
}

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
"""

NETWORK_CONF_FN = "/etc/network/interfaces.d/50-cloud-init"
LOCALE_CONF_FN = "/etc/default/locale"

# The frontend lock needs to be acquired first followed by the order that
# apt uses. /var/lib/apt/lists is locked independently of that install chain,
# and only locked during update, so you can acquire it either order.
# Also update does not acquire the dpkg frontend lock.
# More context:
#   https://github.com/canonical/cloud-init/pull/1034#issuecomment-986971376
APT_LOCK_FILES = [
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/cache/apt/archives/lock",
    "/var/lib/apt/lists/lock",
]


class Distro(distros.Distro):
    hostname_conf_fn = "/etc/hostname"
    network_conf_fn = {
        "eni": "/etc/network/interfaces.d/50-cloud-init",
        "netplan": "/etc/netplan/50-cloud-init.yaml",
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

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "debian"
        self.default_locale = "en_US.UTF-8"
        self.system_locale = None

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
        sys_locale_unset = False if self.system_locale else True
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

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command("install", pkgs=pkglist)

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
            pass
        if not conf:
            conf = HostnameConf("")
        conf.set_hostname(hostname)
        util.write_file(filename, str(conf), 0o644)

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

    def _get_localhost_ip(self):
        # Note: http://www.leonardoborda.com/blog/127-0-1-1-ubuntu-debian/
        return "127.0.1.1"

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def _apt_lock_available(self, lock_files=None):
        """Determines if another process holds any apt locks.

        If all locks are clear, return True else False.
        """
        if lock_files is None:
            lock_files = APT_LOCK_FILES
        for lock in lock_files:
            if not os.path.exists(lock):
                # Only wait for lock files that already exist
                continue
            with open(lock, "w") as handle:
                try:
                    fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return False
        return True

    def _wait_for_apt_command(
        self, short_cmd, subp_kwargs, timeout=APT_LOCK_WAIT_TIMEOUT
    ):
        """Wait for apt install to complete.

        short_cmd: Name of command like "upgrade" or "install"
        subp_kwargs: kwargs to pass to subp
        """
        start_time = time.time()
        LOG.debug("Waiting for apt lock")
        while time.time() - start_time < timeout:
            if not self._apt_lock_available():
                time.sleep(1)
                continue
            LOG.debug("apt lock available")
            try:
                # Allow the output of this to flow outwards (not be captured)
                log_msg = "apt-%s [%s]" % (
                    short_cmd,
                    " ".join(subp_kwargs["args"]),
                )
                return util.log_time(
                    logfunc=LOG.debug,
                    msg=log_msg,
                    func=subp.subp,
                    kwargs=subp_kwargs,
                )
            except subp.ProcessExecutionError:
                # Even though we have already waited for the apt lock to be
                # available, it is possible that the lock was acquired by
                # another process since the check. Since apt doesn't provide
                # a meaningful error code to check and checking the error
                # text is fragile and subject to internationalization, we
                # can instead check the apt lock again. If the apt lock is
                # still available, given the length of an average apt
                # transaction, it is extremely unlikely that another process
                # raced us when we tried to acquire it, so raise the apt
                # error received. If the lock is unavailable, just keep waiting
                if self._apt_lock_available():
                    raise
                LOG.debug("Another process holds apt lock. Waiting...")
                time.sleep(1)
        raise TimeoutError("Could not get apt lock")

    def package_command(self, command, args=None, pkgs=None):
        """Run the given package command.

        On Debian, this will run apt-get (unless APT_GET_COMMAND is set).

        command: The command to run, like "upgrade" or "install"
        args: Arguments passed to apt itself in addition to
              any specified in APT_GET_COMMAND
        pkgs: Apt packages that the command will apply to
        """
        if pkgs is None:
            pkgs = []

        e = os.environ.copy()
        # See: http://manpages.ubuntu.com/manpages/bionic/man7/debconf.7.html
        e["DEBIAN_FRONTEND"] = "noninteractive"

        wcfg = self.get_option("apt_get_wrapper", APT_GET_WRAPPER)
        cmd = _get_wrapper_prefix(
            wcfg.get("command", APT_GET_WRAPPER["command"]),
            wcfg.get("enabled", APT_GET_WRAPPER["enabled"]),
        )

        cmd.extend(list(self.get_option("apt_get_command", APT_GET_COMMAND)))

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        subcmd = command
        if command == "upgrade":
            subcmd = self.get_option(
                "apt_get_upgrade_subcommand", "dist-upgrade"
            )

        cmd.append(subcmd)

        pkglist = util.expand_package_list("%s=%s", pkgs)
        cmd.extend(pkglist)

        self._wait_for_apt_command(
            short_cmd=command,
            subp_kwargs={"args": cmd, "env": e, "capture": False},
        )

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["update"],
            freq=PER_INSTANCE,
        )

    def get_primary_arch(self):
        return util.get_dpkg_architecture()

    def set_keymap(self, layout, model, variant, options):
        # Let localectl take care of updating /etc/default/keyboard
        distros.Distro.set_keymap(self, layout, model, variant, options)
        # Workaround for localectl not applying new settings instantly
        # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=926037
        self.manage_service("restart", "console-setup")


def _get_wrapper_prefix(cmd, mode):
    if isinstance(cmd, str):
        cmd = [str(cmd)]

    if util.is_true(mode) or (
        str(mode).lower() == "auto" and cmd[0] and subp.which(cmd[0])
    ):
        return cmd
    else:
        return []


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
        contents = util.load_file(path)
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
        locale_content = util.load_file(sys_path)
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


# vi: ts=4 expandtab
