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
from cloudinit.net import eni
from cloudinit.net.network_state import parse_net_config_data
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


class Distro(distros.Distro):
    hostname_conf_fn = "/etc/hostname"
    locale_conf_fn = "/etc/default/locale"
    network_conf_fn = "/etc/network/interfaces.d/50-cloud-init.cfg"

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'debian'
        self._net_renderer = eni.Renderer({
            'eni_path': self.network_conf_fn,
            'eni_header': ENI_HEADER,
            'links_path_prefix': None,
            'netrules_path': None,
        })

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self.locale_conf_fn
        util.subp(['locale-gen', locale], capture=False)
        util.subp(['update-locale', locale], capture=False)
        # "" provides trailing newline during join
        lines = [
            util.make_header(),
            'LANG="%s"' % (locale),
            "",
        ]
        util.write_file(out_fn, "\n".join(lines))

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('install', pkgs=pkglist)

    def _write_network(self, settings):
        util.write_file(self.network_conf_fn, settings)
        return ['all']

    def _write_network_config(self, netconfig):
        ns = parse_net_config_data(netconfig)
        self._net_renderer.render_network_state("/", ns)
        _maybe_remove_legacy_eth0()
        return []

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
        # See: http://tiny.cc/kg91fw
        # Or: http://tiny.cc/mh91fw
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

    LOG.warn(msg)

# vi: ts=4 expandtab
