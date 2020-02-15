import platform

from cloudinit import distros
from cloudinit import helpers
from cloudinit import net
from cloudinit.distros import bsd_util


class BSD(distros.Distro):
    hostname_conf_fn = '/etc/rc.conf'
    rc_conf_fn = "/etc/rc.conf"

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
        return bsd_util.get_rc_config_value('hostname')

    def _write_hostname(self, hostname, filename):
        bsd_util.set_rc_config_value('hostname', hostname,
                                     fn='/etc/rc.conf')

    def generate_fallback_config(self):
        nconf = {'config': [], 'version': 1}
        for mac, name in net.get_interfaces_by_mac().items():
            nconf['config'].append(
                {'type': 'physical', 'name': name,
                 'mac_address': mac, 'subnets': [{'type': 'dhcp'}]})
        return nconf

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))
