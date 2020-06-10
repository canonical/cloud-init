# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import log as logging
from cloudinit import subp
from cloudinit import util
import cloudinit.net.bsd

LOG = logging.getLogger(__name__)


class Renderer(cloudinit.net.bsd.BSDRenderer):

    def __init__(self, config=None):
        super(Renderer, self).__init__()

    def write_config(self):
        if self.dhcp_interfaces():
            self.set_rc_config_value('dhcpcd', 'YES')
            self.set_rc_config_value(
                'dhcpcd_flags',
                ' '.join(self.dhcp_interfaces())
            )
        for device_name, v in self.interface_configurations.items():
            if isinstance(v, dict):
                self.set_rc_config_value(
                    'ifconfig_' + device_name,
                    v.get('address') + ' netmask ' + v.get('netmask'))

    def start_services(self, run=False):
        if not run:
            LOG.debug("netbsd generate postcmd disabled")
            return

        subp.subp(['service', 'network', 'restart'], capture=True)
        if self.dhcp_interfaces():
            subp.subp(['service', 'dhcpcd', 'restart'], capture=True)

    def set_route(self, network, netmask, gateway):
        if network == '0.0.0.0':
            self.set_rc_config_value('defaultroute', gateway)


def available(target=None):
    return util.is_NetBSD()
