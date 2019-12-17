# This file is part of cloud-init. See LICENSE file for license information.

import re

from cloudinit import log as logging
from cloudinit import net
from cloudinit import util
from cloudinit.distros import rhel_util
from cloudinit.distros.parsers.resolv_conf import ResolvConf

from . import renderer

LOG = logging.getLogger(__name__)


class Renderer(renderer.Renderer):
    resolv_conf_fn = 'etc/resolv.conf'
    rc_conf_fn = 'etc/rc.conf'

    def __init__(self, config=None):
        if not config:
            config = {}
        self.dhcp_interfaces = []
        self._postcmds = config.get('postcmds', True)

    def _write_ifconfig_entries(self, settings, target=None):
        ifname_by_mac = net.get_interfaces_by_mac()
        for interface in settings.iter_interfaces():
            device_name = interface.get("name")
            device_mac = interface.get("mac_address")
            if device_name and re.match(r'^lo\d+$', device_name):
                continue
            if device_mac and device_name:
                cur_name = ifname_by_mac[device_mac]
                if not cur_name:
                    LOG.info('Cannot find any device with MAC %s', device_mac)
                    continue
                if cur_name != device_name:
                    rhel_util.update_sysconfig_file(
                        util.target_path(target, self.rc_conf_fn), {
                            'ifconfig_%s_name' % cur_name: device_name})
            elif device_mac:
                device_name = ifname_by_mac[device_mac]

            LOG.info('Configuring interface %s', device_name)
            ifconfig = 'DHCP'  # default
            for subnet in interface.get("subnets", []):

                if subnet.get('type') == 'static':
                    LOG.debug('Configuring dev %s with %s / %s', device_name,
                              subnet.get('address'), subnet.get('netmask'))
                # Configure an ipv4 address.
                    ifconfig = (
                            subnet.get('address') + ' netmask ' +
                            subnet.get('netmask'))

                # NOTE: Known limitation, we just set one subnet per interface
                break

            if ifconfig == 'DHCP':
                self.dhcp_interfaces.append(device_name)
            rhel_util.update_sysconfig_file(
                util.target_path(target, self.rc_conf_fn), {
                    'ifconfig_' + device_name: ifconfig})

    def _write_route_entries(self, settings, target=None):
        routes = list(settings.iter_routes())
        for interface in settings.iter_interfaces():
            subnets = interface.get("subnets", [])
            for subnet in subnets:
                if subnet.get('type') == 'static':
                    gateway = subnet.get('gateway')
                    if gateway:
                        routes.append({
                            'network': '0.0.0.0',
                            'netmask': '0.0.0.0',
                            'gateway': gateway})
                    routes += subnet.get('routes', [])
        route_cpt = 0
        for route in routes:
            network = route.get('network')
            netmask = route.get('netmask')
            gateway = route.get('gateway')
            route_cmd = "-route %s/%s %s" % (network, netmask, gateway)
            if not network:
                continue
            if network == '0.0.0.0':
                rhel_util.update_sysconfig_file(
                    util.target_path(target, self.rc_conf_fn), {
                        'defaultrouter': gateway})
            else:
                rhel_util.update_sysconfig_file(
                    util.target_path(target, self.rc_conf_fn), {
                        'route_net%d' % route_cpt: route_cmd})
                route_cpt += 1

    def _write_resolve_conf(self, settings, target=None):
        nameservers = settings.dns_nameservers
        searchdomains = settings.dns_searchdomains
        for interface in settings.iter_interfaces():
            for subnet in interface.get("subnets", []):
                if 'dns_nameservers' in subnet:
                    nameservers.extend(subnet['dns_nameservers'])
                if 'dns_search' in subnet:
                    searchdomains.extend(subnet['dns_search'])
        # Try to read the /etc/resolv.conf or just start from scratch if that
        # fails.
        try:
            resolvconf = ResolvConf(util.load_file(self.resolv_conf_fn))
            resolvconf.parse()
        except IOError:
            util.logexc(LOG, "Failed to parse %s, use new empty file",
                        self.resolv_conf_fn)
            resolvconf = ResolvConf('')
            resolvconf.parse()

        # Add some nameservers
        for server in nameservers:
            try:
                resolvconf.add_nameserver(server)
            except ValueError:
                util.logexc(LOG, "Failed to add nameserver %s", server)

        # And add any searchdomains.
        for domain in searchdomains:
            try:
                resolvconf.add_search_domain(domain)
            except ValueError:
                util.logexc(LOG, "Failed to add search domain %s", domain)
        util.write_file(
            util.target_path(target, self.resolv_conf_fn),
            str(resolvconf), 0o644)

    def _write_network(self, settings, target=None):
        self._write_ifconfig_entries(settings, target=None)
        self._write_route_entries(settings, target=None)
        self._write_resolve_conf(settings, target=None)

        self.start_services()

    def render_network_state(self, network_state, templates=None, target=None):
        self._write_network(network_state, target=target)

    def start_services(self):
        if not self._postcmds:
            LOG.debug("freebsd generate postcmd disabled")
            return

        util.subp(['service', 'netif', 'restart'], capture=True)
        util.subp(['service', 'routing', 'restart'], capture=True)
        for dhcp_interface in self.dhcp_interfaces:
            util.subp(['service', 'dhclient', 'restart', dhcp_interface],
                      capture=True)


def available(target=None):
    return util.is_FreeBSD()
