import platform

from cloudinit import distros
from cloudinit.distros import bsd_utils
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import net
from cloudinit import subp
from cloudinit import util
from .networking import BSDNetworking

LOG = logging.getLogger(__name__)


class BSD(distros.Distro):
    networking_cls = BSDNetworking
    hostname_conf_fn = '/etc/rc.conf'
    rc_conf_fn = "/etc/rc.conf"

    # This differs from the parent Distro class, which has -P for
    # poweroff.
    shutdown_options_map = {'halt': '-H', 'poweroff': '-p', 'reboot': '-r'}

    # Set in BSD distro subclasses
    group_add_cmd_prefix = []
    pkg_cmd_install_prefix = []
    pkg_cmd_remove_prefix = []
    # There is no update/upgrade on OpenBSD
    pkg_cmd_update_prefix = None
    pkg_cmd_upgrade_prefix = None

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        cfg['ssh_svcname'] = 'sshd'
        self.osfamily = platform.system().lower()

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname(self, filename, default=None):
        return bsd_utils.get_rc_config_value('hostname')

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        raise NotImplementedError('Return list cmd to add member to group')

    def _write_hostname(self, hostname, filename):
        bsd_utils.set_rc_config_value('hostname', hostname, fn='/etc/rc.conf')

    def create_group(self, name, members=None):
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            group_add_cmd = self.group_add_cmd_prefix + [name]
            try:
                subp.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)

        if not members:
            members = []
        for member in members:
            if not util.is_user(member):
                LOG.warning("Unable to add group member '%s' to group '%s'"
                            "; user does not exist.", member, name)
                continue
            try:
                subp.subp(self._get_add_member_to_group_cmd(member, name))
                LOG.info("Added user '%s' to group '%s'", member, name)
            except Exception:
                util.logexc(LOG, "Failed to add user '%s' to group '%s'",
                            member, name)

    def generate_fallback_config(self):
        nconf = {'config': [], 'version': 1}
        for mac, name in net.get_interfaces_by_mac().items():
            nconf['config'].append(
                {'type': 'physical', 'name': name,
                 'mac_address': mac, 'subnets': [{'type': 'dhcp'}]})
        return nconf

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('install', pkgs=pkglist)

    def _get_pkg_cmd_environ(self):
        """Return environment vars used in *BSD package_command operations"""
        raise NotImplementedError('BSD subclasses return a dict of env vars')

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        if command == 'install':
            cmd = self.pkg_cmd_install_prefix
        elif command == 'remove':
            cmd = self.pkg_cmd_remove_prefix
        elif command == 'update':
            if not self.pkg_cmd_update_prefix:
                return
            cmd = self.pkg_cmd_update_prefix
        elif command == 'upgrade':
            if not self.pkg_cmd_upgrade_prefix:
                return
            cmd = self.pkg_cmd_upgrade_prefix

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, env=self._get_pkg_cmd_environ(), capture=False)

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def apply_locale(self, locale, out_fn=None):
        LOG.debug('Cannot set the locale.')

    def apply_network_config_names(self, netconfig):
        LOG.debug('Cannot rename network interface.')
