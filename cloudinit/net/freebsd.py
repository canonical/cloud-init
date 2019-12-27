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

    def _update_rc_conf(self, settings, target=None):
        fn = util.target_path(target, self.rc_conf_fn)
        rhel_util.update_sysconfig_file(fn, settings)

    def _write_ifconfig_entries(self, settings, target=None):
        ifname_by_mac = net.get_interfaces_by_mac()
        for interface in settings.iter_interfaces():
            device_name = interface.get("name")
            device_mac = interface.get("mac_address")
            if device_name and re.match(r'^lo\d+$', device_name):
                continue
            if device_mac not in ifname_by_mac:
                LOG.info('Cannot find any device with MAC %s', device_mac)
            elif device_mac and device_name:
                cur_name = ifname_by_mac[device_mac]
                if cur_name != device_name:
                    LOG.info('netif service will rename interface %s to %s',
                             cur_name, device_name)
                    self._update_rc_conf(
                        {'ifconfig_%s_name' % cur_name: device_name},
                        target=target)
            else:
                device_name = ifname_by_mac[device_mac]

            LOG.info('Configuring interface %s', device_name)
            ifconfig = 'DHCP'  # default

            for subnet in interface.get("subnets", []):
                if ifconfig != 'DHCP':
                    LOG.info('The FreeBSD provider only set the first subnet.')
                    break
                if subnet.get('type') == 'static':
                    if not subnet.get('netmask'):
                        LOG.debug(
                                'Skipping IP %s, because there is no netmask',
                                subnet.get('address'))
                        continue
                    LOG.debug('Configuring dev %s with %s / %s', device_name,
                              subnet.get('address'), subnet.get('netmask'))
                # Configure an ipv4 address.
                    ifconfig = (
                            subnet.get('address') + ' netmask ' +
                            subnet.get('netmask'))

            if ifconfig == 'DHCP':
                self.dhcp_interfaces.append(device_name)
            self._update_rc_conf(
                {'ifconfig_' + device_name: ifconfig},
                target=target)

    def _write_route_entries(self, settings, target=None):
        routes = list(settings.iter_routes())
        for interface in settings.iter_interfaces():
            subnets = interface.get("subnets", [])
            for subnet in subnets:
                if subnet.get('type') != 'static':
                    continue
                gateway = subnet.get('gateway')
                if gateway and len(gateway.split('.')) == 4:
                    routes.append({
                        'network': '0.0.0.0',
                        'netmask': '0.0.0.0',
                        'gateway': gateway})
                routes += subnet.get('routes', [])
        route_cpt = 0
        for route in routes:
            network = route.get('network')
            if not network:
                LOG.debug('Skipping a bad route entry')
                continue
            netmask = route.get('netmask')
            gateway = route.get('gateway')
            route_cmd = "-route %s/%s %s" % (network, netmask, gateway)
            if network == '0.0.0.0':
                self._update_rc_conf(
                    {'defaultrouter': gateway}, target=target)
            else:
                self._update_rc_conf(
                    {'route_net%d' % route_cpt: route_cmd}, target=target)
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
            resolvconf = ResolvConf(util.load_file(util.target_path(
                target, self.resolv_conf_fn)))
            resolvconf.parse()
        except IOError:
            util.logexc(LOG, "Failed to parse %s, use new empty file",
                        util.target_path(target, self.resolv_conf_fn))
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
        self._write_ifconfig_entries(settings, target=target)
        self._write_route_entries(settings, target=target)
        self._write_resolve_conf(settings, target=target)

        self.start_services(run=self._postcmds)

    def render_network_state(self, network_state, templates=None, target=None):
        self._write_network(network_state, target=target)

    def start_services(self, run=False):
        if not run:
            LOG.debug("freebsd generate postcmd disabled")
            return

        util.subp(['service', 'netif', 'restart'], capture=True)
        # On FreeBSD 10, the restart of routing and dhclient is likely to fail
        # because
        # - routing: it cannot remove the loopback route, but it will still set
        #   up the default route as expected.
        # - dhclient: it cannot stop the dhclient started by the netif service.
        # In both case, the situation is ok, and we can proceed.
        util.subp(['service', 'routing', 'restart'], capture=True, rcs=[0, 1])
        for dhcp_interface in self.dhcp_interfaces:
            util.subp(['service', 'dhclient', 'restart', dhcp_interface],
                      rcs=[0, 1],
                      capture=True)


def available(target=None):
    return util.is_FreeBSD()
