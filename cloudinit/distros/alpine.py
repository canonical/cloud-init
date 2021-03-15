# Copyright (C) 2016 Matt Dainty
# Copyright (C) 2020 Dermot Bradley
#
# Author: Matt Dainty <matt@bodgit-n-scarper.com>
# Author: Dermot Bradley <dermot_bradley@yahoo.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit import helpers
from cloudinit import subp
from cloudinit import util

from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit.settings import PER_INSTANCE

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource. Changes
# to it will not persist across an instance reboot. To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}

"""


class Distro(distros.Distro):
    init_cmd = ['rc-service']  # init scripts
    locale_conf_fn = "/etc/profile.d/locale.sh"
    network_conf_fn = "/etc/network/interfaces"
    renderer_configs = {
        "eni": {"eni_path": network_conf_fn,
                "eni_header": NETWORK_FILE_HEADER}
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.default_locale = 'C.UTF-8'
        self.osfamily = 'alpine'
        cfg['ssh_svcname'] = 'sshd'

    def get_locale(self):
        """The default locale for Alpine Linux is different than
           cloud-init's DataSource default.
        """
        return self.default_locale

    def apply_locale(self, locale, out_fn=None):
        # Alpine has limited locale support due to musl library limitations

        if not locale:
            locale = self.default_locale
        if not out_fn:
            out_fn = self.locale_conf_fn

        lines = [
            "#",
            "# This file is created by cloud-init once per new instance boot",
            "#",
            "export CHARSET=UTF-8",
            "export LANG=%s" % locale,
            "export LC_COLLATE=C",
            "",
        ]
        util.write_file(out_fn, "\n".join(lines), 0o644)

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('add', pkgs=pkglist)

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    def _bring_up_interfaces(self, device_names):
        use_all = False
        for d in device_names:
            if d == 'all':
                use_all = True
        if use_all:
            return distros.Distro._bring_up_interface(self, '-a')
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
        return "127.0.1.1"

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['apk']
        # Redirect output
        cmd.append("--quiet")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["update"], freq=PER_INSTANCE)

    @property
    def preferred_ntp_clients(self):
        """Allow distro to determine the preferred ntp client list"""
        if not self._preferred_ntp_clients:
            self._preferred_ntp_clients = ['chrony', 'ntp']

        return self._preferred_ntp_clients

    def shutdown_command(self, mode='poweroff', delay='now', message=None):
        # called from cc_power_state_change.load_power_state
        # Alpine has halt/poweroff/reboot, with the following specifics:
        # - we use them rather than the generic "shutdown"
        # - delay is given with "-d [integer]"
        # - the integer is in seconds, cannot be "now", and takes no "+"
        # - no message is supported (argument ignored, here)

        command = [mode, "-d"]

        # Convert delay from minutes to seconds, as Alpine's
        # halt/poweroff/reboot commands take seconds rather than minutes.
        if delay == "now":
            # Alpine's commands do not understand "now".
            command += ['0']
        else:
            try:
                command.append(str(int(delay) * 60))
            except ValueError as e:
                raise TypeError(
                    "power_state[delay] must be 'now' or '+m' (minutes)."
                    " found '%s'." % (delay,)
                ) from e

        return command

# vi: ts=4 expandtab
