# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

APT_GET_COMMAND = ('apt-get', '--option=Dpkg::Options::=--force-confold',
                   '--option=Dpkg::options::=--force-unsafe-io',
                   '--assume-yes', '--quiet')
APT_GET_WRAPPER = {
    'command': 'eatmydata',
    'enabled': 'auto',
}

ENI_HEADER = """# This file is generated from information provided by
# the datasource.  Changes to it will not persist across an instance.
# To disable cloud-init's network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
"""

NETWORK_CONF_FN = "/etc/network/interfaces.d/50-cloud-init.cfg"
LOCALE_CONF_FN = "/etc/default/locale"


class Distro(distros.Distro):
    hostname_conf_fn = "/etc/hostname"
    network_conf_fn = {
        "eni": "/etc/network/interfaces.d/50-cloud-init.cfg",
        "netplan": "/etc/netplan/50-cloud-init.yaml"
    }
    renderer_configs = {
        "eni": {"eni_path": network_conf_fn["eni"],
                "eni_header": ENI_HEADER},
        "netplan": {"netplan_path": network_conf_fn["netplan"],
                    "netplan_header": ENI_HEADER,
                    "postcmds": True}
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'debian'
        self.default_locale = 'en_US.UTF-8'
        self.system_locale = None

    def get_locale(self):
        """Return the default locale if set, else use default locale"""

        # read system locale value
        if not self.system_locale:
            self.system_locale = read_system_locale()

        # Return system_locale setting if valid, else use default locale
        return (self.system_locale if self.system_locale else
                self.default_locale)

    def apply_locale(self, locale, out_fn=None, keyname='LANG'):
        """Apply specified locale to system, regenerate if specified locale
            differs from system default."""
        if not out_fn:
            out_fn = LOCALE_CONF_FN

        if not locale:
            raise ValueError('Failed to provide locale value.')

        # Only call locale regeneration if needed
        # Update system locale config with specified locale if needed
        distro_locale = self.get_locale()
        conf_fn_exists = os.path.exists(out_fn)
        sys_locale_unset = False if self.system_locale else True
        need_regen = (locale.lower() != distro_locale.lower() or
                      not conf_fn_exists or sys_locale_unset)
        need_conf = not conf_fn_exists or need_regen or sys_locale_unset

        if need_regen:
            regenerate_locale(locale, out_fn, keyname=keyname)
        else:
            LOG.debug(
                "System has '%s=%s' requested '%s', skipping regeneration.",
                keyname, self.system_locale, locale)

        if need_conf:
            update_locale_conf(locale, out_fn, keyname=keyname)
            # once we've updated the system config, invalidate cache
            self.system_locale = None

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('install', pkgs=pkglist)

    def _write_network(self, settings):
        # this is a legacy method, it will always write eni
        util.write_file(self.network_conf_fn["eni"], settings)
        return ['all']

    def _write_network_config(self, netconfig):
        _maybe_remove_legacy_eth0()
        return self._supported_write_network_config(netconfig)

    def _bring_up_interfaces(self, device_names):
        use_all = False
        for d in device_names:
            if d == 'all':
                use_all = True
        if use_all:
            return distros.Distro._bring_up_interface(self, '--all')
        else:
            return distros.Distro._bring_up_interfaces(self, device_names)

    def _write_hostname(self, your_hostname, out_fn):
        conf = None
        try:
            # Try to update the previous one
            # so lets see if we can read it first.
            conf = self._read_hostname_conf(out_fn)
        except IOError:
            pass
        if not conf:
            conf = HostnameConf('')
        conf.set_hostname(your_hostname)
        util.write_file(out_fn, str(conf), 0o644)

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

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        e = os.environ.copy()
        # See: http://manpages.ubuntu.com/manpages/xenial/man7/debconf.7.html
        e['DEBIAN_FRONTEND'] = 'noninteractive'

        wcfg = self.get_option("apt_get_wrapper", APT_GET_WRAPPER)
        cmd = _get_wrapper_prefix(
            wcfg.get('command', APT_GET_WRAPPER['command']),
            wcfg.get('enabled', APT_GET_WRAPPER['enabled']))

        cmd.extend(list(self.get_option("apt_get_command", APT_GET_COMMAND)))

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        subcmd = command
        if command == "upgrade":
            subcmd = self.get_option("apt_get_upgrade_subcommand",
                                     "dist-upgrade")

        cmd.append(subcmd)

        pkglist = util.expand_package_list('%s=%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.log_time(logfunc=LOG.debug,
                      msg="apt-%s [%s]" % (command, ' '.join(cmd)),
                      func=util.subp,
                      args=(cmd,), kwargs={'env': e, 'capture': False})

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["update"], freq=PER_INSTANCE)

    def get_primary_arch(self):
        (arch, _err) = util.subp(['dpkg', '--print-architecture'])
        return str(arch).strip()


def _get_wrapper_prefix(cmd, mode):
    if isinstance(cmd, str):
        cmd = [str(cmd)]

    if (util.is_true(mode) or
        (str(mode).lower() == "auto" and cmd[0] and
         util.which(cmd[0]))):
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
        lines = [f.strip() for f in contents.splitlines()
                 if not f.startswith("#")]
        if lines == known_contents:
            util.del_file(path)
            msg = "removed %s with known contents" % path
        else:
            msg = (bmsg + " '%s' exists with user configured content." % path)
    except Exception:
        msg = bmsg + " %s exists, but could not be read." % path

    LOG.warning(msg)


def read_system_locale(sys_path=LOCALE_CONF_FN, keyname='LANG'):
    """Read system default locale setting, if present"""
    sys_val = ""
    if not sys_path:
        raise ValueError('Invalid path: %s' % sys_path)

    if os.path.exists(sys_path):
        locale_content = util.load_file(sys_path)
        sys_defaults = util.load_shell_content(locale_content)
        sys_val = sys_defaults.get(keyname, "")

    return sys_val


def update_locale_conf(locale, sys_path, keyname='LANG'):
    """Update system locale config"""
    LOG.debug('Updating %s with locale setting %s=%s',
              sys_path, keyname, locale)
    util.subp(
        ['update-locale', '--locale-file=' + sys_path,
         '%s=%s' % (keyname, locale)], capture=False)


def regenerate_locale(locale, sys_path, keyname='LANG'):
    """
    Run locale-gen for the provided locale and set the default
    system variable `keyname` appropriately in the provided `sys_path`.

    """
    # special case for locales which do not require regen
    # % locale -a
    # C
    # C.UTF-8
    # POSIX
    if locale.lower() in ['c', 'c.utf-8', 'posix']:
        LOG.debug('%s=%s does not require rengeneration', keyname, locale)
        return

    # finally, trigger regeneration
    LOG.debug('Generating locales for %s', locale)
    util.subp(['locale-gen', locale], capture=False)


# vi: ts=4 expandtab
