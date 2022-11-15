# Copyright (C) 2016 Matt Dainty
# Copyright (C) 2020 Dermot Bradley
#
# Author: Matt Dainty <matt@bodgit-n-scarper.com>
# Author: Dermot Bradley <dermot_bradley@yahoo.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros, helpers, subp, util
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
    pip_package_name = "py3-pip"
    locale_conf_fn = "/etc/profile.d/locale.sh"
    network_conf_fn = "/etc/network/interfaces"
    renderer_configs = {
        "eni": {"eni_path": network_conf_fn, "eni_header": NETWORK_FILE_HEADER}
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.default_locale = "C.UTF-8"
        self.osfamily = "alpine"
        cfg["ssh_svcname"] = "sshd"

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
        self.package_command("add", pkgs=pkglist)

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
        return "127.0.1.1"

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ["apk"]
        # Redirect output
        cmd.append("--quiet")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        if command == "upgrade":
            cmd.extend(["--update-cache", "--available"])

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["update"],
            freq=PER_INSTANCE,
        )

    @property
    def preferred_ntp_clients(self):
        """Allow distro to determine the preferred ntp client list"""
        if not self._preferred_ntp_clients:
            self._preferred_ntp_clients = ["chrony", "ntp"]

        return self._preferred_ntp_clients

    def shutdown_command(self, mode="poweroff", delay="now", message=None):
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
            command += ["0"]
        else:
            try:
                command.append(str(int(delay) * 60))
            except ValueError as e:
                raise TypeError(
                    "power_state[delay] must be 'now' or '+m' (minutes)."
                    " found '%s'." % (delay,)
                ) from e

        return command

    def uses_systemd(self):
        """
        Alpine uses OpenRC, not systemd
        """
        return False

    def manage_service(self, action: str, service: str):
        """
        Perform the requested action on a service. This handles OpenRC
        specific implementation details.

        OpenRC has two distinct commands relating to services,
        'rc-service' and 'rc-update' and the order of their argument
        lists differ.
        May raise ProcessExecutionError
        """
        init_cmd = ["rc-service", "--nocolor"]
        update_cmd = ["rc-update", "--nocolor"]
        cmds = {
            "stop": list(init_cmd) + [service, "stop"],
            "start": list(init_cmd) + [service, "start"],
            "disable": list(update_cmd) + ["del", service],
            "enable": list(update_cmd) + ["add", service],
            "restart": list(init_cmd) + [service, "restart"],
            "reload": list(init_cmd) + [service, "restart"],
            "try-reload": list(init_cmd) + [service, "restart"],
            "status": list(init_cmd) + [service, "status"],
        }
        cmd = list(cmds[action])
        return subp.subp(cmd, capture=True)
