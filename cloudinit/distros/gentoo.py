# Copyright (C) 2014 Rackspace, US Inc.
# Copyright (C) 2016 Matthew Thode.
#
# Author: Nate House <nathan.house@rackspace.com>
# Author: Matthew Thode <prometheanfire@gentoo.org>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros, helpers
from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.distros import net_util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    locale_conf_fn = "/etc/env.d/02locale"
    locale_gen_fn = "/etc/locale.gen"
    network_conf_fn = "/etc/conf.d/net"
    hostname_conf_fn = "/etc/conf.d/hostname"
    init_cmd = ["rc-service"]  # init scripts
    default_locale = "en_US.UTF-8"

    # C.UTF8 makes sense to generate, but is not selected
    # Add /etc/locale.gen entries to this list to support more locales
    locales = ["C.UTF8 UTF-8", "en_US.UTF-8 UTF-8"]

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
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

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command("", pkgs=pkglist)

    def _write_network(self, settings):
        entries = net_util.translate_network(settings)
        LOG.debug(
            "Translated ubuntu style network settings %s into %s",
            settings,
            entries,
        )
        dev_names = entries.keys()
        nameservers = []

        for (dev, info) in entries.items():
            if "dns-nameservers" in info:
                nameservers.extend(info["dns-nameservers"])
            if dev == "lo":
                continue
            net_fn = self.network_conf_fn + "." + dev
            dns_nameservers = info.get("dns-nameservers")
            if isinstance(dns_nameservers, (list, tuple)):
                dns_nameservers = str(tuple(dns_nameservers)).replace(",", "")
            # eth0, {'auto': True, 'ipv6': {}, 'bootproto': 'dhcp'}
            # lo, {'dns-nameservers': ['10.0.1.3'], 'ipv6': {}, 'auto': True}
            results = ""
            if info.get("bootproto") == "dhcp":
                results += 'config_{name}="dhcp"'.format(name=dev)
            else:
                results += (
                    'config_{name}="{ip_address} netmask {netmask}"\n'
                    'mac_{name}="{hwaddr}"\n'
                ).format(
                    name=dev,
                    ip_address=info.get("address"),
                    netmask=info.get("netmask"),
                    hwaddr=info.get("hwaddress"),
                )
                results += 'routes_{name}="default via {gateway}"\n'.format(
                    name=dev, gateway=info.get("gateway")
                )
            if info.get("dns-nameservers"):
                results += 'dns_servers_{name}="{dnsservers}"\n'.format(
                    name=dev, dnsservers=dns_nameservers
                )
            util.write_file(net_fn, results)
            self._create_network_symlink(dev)
            if info.get("auto"):
                cmd = [
                    "rc-update",
                    "add",
                    "net.{name}".format(name=dev),
                    "default",
                ]
                try:
                    (_out, err) = subp.subp(cmd)
                    if len(err):
                        LOG.warning(
                            "Running %s resulted in stderr output: %s",
                            cmd,
                            err,
                        )
                except subp.ProcessExecutionError:
                    util.logexc(
                        LOG, "Running interface command %s failed", cmd
                    )

        if nameservers:
            util.write_file(
                self.resolve_conf_fn, convert_resolv_conf(nameservers)
            )

        return dev_names

    @staticmethod
    def _create_network_symlink(interface_name):
        file_path = "/etc/init.d/net.{name}".format(name=interface_name)
        if not util.is_link(file_path):
            util.sym_link("/etc/init.d/net.lo", file_path)

    def _bring_up_interface(self, device_name):
        cmd = ["/etc/init.d/net.%s" % device_name, "restart"]
        LOG.debug(
            "Attempting to run bring up interface %s using command %s",
            device_name,
            cmd,
        )
        try:
            (_out, err) = subp.subp(cmd)
            if len(err):
                LOG.warning(
                    "Running %s resulted in stderr output: %s", cmd, err
                )
            return True
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _bring_up_interfaces(self, device_names):
        use_all = False
        for d in device_names:
            if d == "all":
                use_all = True
        if use_all:
            # Grab device names from init scripts
            cmd = ["ls", "/etc/init.d/net.*"]
            try:
                (_out, err) = subp.subp(cmd)
                if len(err):
                    LOG.warning(
                        "Running %s resulted in stderr output: %s", cmd, err
                    )
            except subp.ProcessExecutionError:
                util.logexc(LOG, "Running interface command %s failed", cmd)
                return False
            devices = [x.split(".")[2] for x in _out.split("  ")]
            return distros.Distro._bring_up_interfaces(self, devices)
        else:
            return distros.Distro._bring_up_interfaces(self, device_names)

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

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        cmd = list("emerge")
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

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["--sync"],
            freq=PER_INSTANCE,
        )


def convert_resolv_conf(settings):
    """Returns a settings string formatted for resolv.conf."""
    result = ""
    if isinstance(settings, list):
        for ns in settings:
            result += "nameserver %s\n" % ns
    return result


# vi: ts=4 expandtab
