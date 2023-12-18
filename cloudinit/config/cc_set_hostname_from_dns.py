# =================================================================
# Licensed Materials - Property of IBM
#
# (c) Copyright IBM Corp. 2015 All Rights Reserved
#
# US Government Users Restricted Rights - Use, duplication or
# disclosure restricted by GSA ADP Schedule Contract with IBM Corp.
# =================================================================

from cloudinit.settings import PER_INSTANCE
from cloudinit import util
from cloudinit import netinfo
import socket


frequency = PER_INSTANCE


def handle(name, _cfg, _cloud, log, _args):
    default_interface = 'eth0'
    system_info = util.system_info()
    if 'aix' in system_info['platform'].lower():
        default_interface = 'en0'

    interface = util.get_cfg_option_str(_cfg,
                                        'set_hostname_from_interface',
                                        default=default_interface)
    log.debug('Setting hostname based on interface %s' % interface)
    set_hostname = False
    fqdn = None
    # Look up the IP address on the interface
    # and then reverse lookup the hostname in DNS
    info = netinfo.netdev_info()
    if interface in info:
        set_short = util.get_cfg_option_bool(_cfg, "set_dns_shortname", False)
        if 'ipv4' in info[interface] and  info[interface]['ipv4']:
            # Handle IPv4 address from network_eni format
            ipv4 = info[interface]['ipv4']
            set_hostname =_set_hostname(_cfg, _cloud, log,
                                        ipv4[0]['ip'], set_short)
        elif 'addr' in info[interface] and info[interface]['addr']:
            # Handle IPv4 address
            set_hostname =_set_hostname(_cfg, _cloud, log,
                                        info[interface]['addr'], set_short)
        elif 'addr6' in info[interface] and info[interface]['addr6']:
            # Handle IPv6 addresses
            for ipaddr in info[interface]['addr6']:
                ipaddr = ipaddr.split('/')[0]
                set_hostname = _set_hostname(_cfg, _cloud, log, ipaddr,
                                             set_short)
                if set_hostname:
                    break
    else:
        log.warning('Interface %s was not found on the system. '
                    'Interfaces found on system: %s' % (interface,
                                                        list(info.keys())))

    # Reverse lookup failed, fall back to cc_set_hostname way.
    if not set_hostname:
        (short_hostname, fqdn) = util.get_hostname_fqdn(_cfg, _cloud)
        try:
            log.info('Fall back to setting hostname on VM as %s' % fqdn)
            _cloud.distro.set_hostname(short_hostname, fqdn=fqdn)
        except Exception:
            util.logexc(log, "Failed to set the hostname to %s", fqdn)
            raise


def _set_hostname(_cfg, _cloud, log, ipaddr, set_short):
    log.debug('ipaddr: %s' % ipaddr)
    try:
        addrinfo = socket.getaddrinfo(ipaddr, None, 0, socket.SOCK_STREAM)
        log.debug('addrinfo: %s' % addrinfo)
        if addrinfo:
            (fqdn, port) = socket.getnameinfo(addrinfo[0][4],
                                              socket.NI_NAMEREQD)
            if fqdn:
                log.info('Setting hostname on VM as %s' % fqdn)
                hostname = fqdn.split('.')[0] if set_short else fqdn
                _cloud.distro.set_hostname(hostname, fqdn=hostname)
                return True
    except socket.error:
        log.warning('No hostname found for IP address %s' % ipaddr)
    except socket.gaierror:
        log.warning('Unable to resolve hostname for IP address %s' % ipaddr)
    return False
