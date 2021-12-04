# This file is part of cloud-init. See LICENSE file for license information.

import platform

import cloudinit.net.bsd
from cloudinit import log as logging
from cloudinit import subp, util

LOG = logging.getLogger(__name__)


class Renderer(cloudinit.net.bsd.BSDRenderer):
    def write_config(self):
        for device_name, v in self.interface_configurations.items():
            if_file = "etc/hostname.{}".format(device_name)
            fn = subp.target_path(self.target, if_file)
            if device_name in self.dhcp_interfaces():
                content = "dhcp\n"
            elif isinstance(v, dict):
                try:
                    content = "inet {address} {netmask}".format(
                        address=v["address"], netmask=v["netmask"]
                    )
                except KeyError:
                    LOG.error(
                        "Invalid static configuration for %s", device_name
                    )
                mtu = v.get("mtu")
                if mtu:
                    content += " mtu %d" % mtu
                content += "\n"
            util.write_file(fn, content)

    def start_services(self, run=False):
        has_dhcpleasectl = bool(int(platform.release().split(".")[0]) > 6)
        if not self._postcmds:
            LOG.debug("openbsd generate postcmd disabled")
            return
        if has_dhcpleasectl:  # OpenBSD 7.0+
            subp.subp(["sh", "/etc/netstart"], capture=True)
            for interface in self.dhcp_interfaces():
                subp.subp(
                    ["dhcpleasectl", "-w", "30", interface], capture=True
                )
        else:
            subp.subp(["pkill", "dhclient"], capture=True, rcs=[0, 1])
            subp.subp(["route", "del", "default"], capture=True, rcs=[0, 1])
            subp.subp(["route", "flush", "default"], capture=True, rcs=[0, 1])
            subp.subp(["sh", "/etc/netstart"], capture=True)

    def set_route(self, network, netmask, gateway):
        if network == "0.0.0.0":
            if_file = "etc/mygate"
            fn = subp.target_path(self.target, if_file)
            content = gateway + "\n"
            util.write_file(fn, content)


def available(target=None):
    return util.is_OpenBSD()
