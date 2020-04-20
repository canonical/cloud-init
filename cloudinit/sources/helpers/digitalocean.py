# Author: Ben Howard  <bh@digitalocean.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json
import random

from cloudinit import log as logging
from cloudinit import net as cloudnet
from cloudinit import url_helper
from cloudinit import util

NIC_MAP = {'public': 'eth0', 'private': 'eth1'}

LOG = logging.getLogger(__name__)


def assign_ipv4_link_local(nic=None):
    """Bring up NIC using an address using link-local (ip4LL) IPs. On
       DigitalOcean, the link-local domain is per-droplet routed, so there
       is no risk of collisions. However, to be more safe, the ip4LL
       address is random.
    """

    if not nic:
        nic = get_link_local_nic()
        LOG.debug("selected interface '%s' for reading metadata", nic)

    if not nic:
        raise RuntimeError("unable to find interfaces to access the"
                           "meta-data server. This droplet is broken.")

    addr = "169.254.{0}.{1}/16".format(random.randint(1, 168),
                                       random.randint(0, 255))

    ip_addr_cmd = ['ip', 'addr', 'add', addr, 'dev', nic]
    ip_link_cmd = ['ip', 'link', 'set', 'dev', nic, 'up']

    if not util.which('ip'):
        raise RuntimeError("No 'ip' command available to configure ip4LL "
                           "address")

    try:
        util.subp(ip_addr_cmd)
        LOG.debug("assigned ip4LL address '%s' to '%s'", addr, nic)
        util.subp(ip_link_cmd)
        LOG.debug("brought device '%s' up", nic)
    except Exception:
        util.logexc(LOG, "ip4LL address assignment of '%s' to '%s' failed."
                         " Droplet networking will be broken", addr, nic)
        raise

    return nic


def get_link_local_nic():
    nics = [f for f in cloudnet.get_devicelist() if cloudnet.is_physical(f)]
    if not nics:
        return None
    return min(nics, key=lambda d: cloudnet.read_sys_net_int(d, 'ifindex'))


def del_ipv4_link_local(nic=None):
    """Remove the ip4LL address. While this is not necessary, the ip4LL
       address is extraneous and confusing to users.
    """
    if not nic:
        LOG.debug("no link_local address interface defined, skipping link "
                  "local address cleanup")
        return

    LOG.debug("cleaning up ipv4LL address")

    ip_addr_cmd = ['ip', 'addr', 'flush', 'dev', nic]

    try:
        util.subp(ip_addr_cmd)
        LOG.debug("removed ip4LL addresses from %s", nic)

    except Exception as e:
        util.logexc(LOG, "failed to remove ip4LL address from '%s'.", nic, e)


def convert_network_configuration(config, dns_servers):
    """Convert the DigitalOcean Network description into Cloud-init's netconfig
       format.

       Example JSON:
        {'public': [
              {'mac': '04:01:58:27:7f:01',
               'ipv4': {'gateway': '45.55.32.1',
                        'netmask': '255.255.224.0',
                        'ip_address': '45.55.50.93'},
               'anchor_ipv4': {
                        'gateway': '10.17.0.1',
                        'netmask': '255.255.0.0',
                        'ip_address': '10.17.0.9'},
               'type': 'public',
               'ipv6': {'gateway': '....',
                        'ip_address': '....',
                        'cidr': 64}}
           ],
          'private': [
              {'mac': '04:01:58:27:7f:02',
               'ipv4': {'gateway': '10.132.0.1',
                        'netmask': '255.255.0.0',
                        'ip_address': '10.132.75.35'},
               'type': 'private'}
           ]
        }
    """

    def _get_subnet_part(pcfg):
        subpart = {'type': 'static',
                   'control': 'auto',
                   'address': pcfg.get('ip_address'),
                   'gateway': pcfg.get('gateway')}

        if ":" in pcfg.get('ip_address'):
            subpart['address'] = "{0}/{1}".format(pcfg.get('ip_address'),
                                                  pcfg.get('cidr'))
        else:
            subpart['netmask'] = pcfg.get('netmask')

        return subpart

    nic_configs = []
    macs_to_nics = cloudnet.get_interfaces_by_mac()
    LOG.debug("nic mapping: %s", macs_to_nics)

    for n in config:
        nic = config[n][0]
        LOG.debug("considering %s", nic)

        mac_address = nic.get('mac')
        if mac_address not in macs_to_nics:
            raise RuntimeError("Did not find network interface on system "
                               "with mac '%s'. Cannot apply configuration: %s"
                               % (mac_address, nic))

        sysfs_name = macs_to_nics.get(mac_address)
        nic_type = nic.get('type', 'unknown')

        if_name = NIC_MAP.get(nic_type, sysfs_name)
        if if_name != sysfs_name:
            LOG.debug("Found %s interface '%s' on '%s', assigned name of '%s'",
                      nic_type, mac_address, sysfs_name, if_name)
        else:
            msg = ("Found interface '%s' on '%s', which is not a public "
                   "or private interface. Using default system naming.")
            LOG.debug(msg, mac_address, sysfs_name)

        ncfg = {'type': 'physical',
                'mac_address': mac_address,
                'name': if_name}

        subnets = []
        for netdef in ('ipv4', 'ipv6', 'anchor_ipv4', 'anchor_ipv6'):
            raw_subnet = nic.get(netdef, None)
            if not raw_subnet:
                continue

            sub_part = _get_subnet_part(raw_subnet)
            if nic_type != "public" or "anchor" in netdef:
                del sub_part['gateway']

            subnets.append(sub_part)

        ncfg['subnets'] = subnets
        nic_configs.append(ncfg)
        LOG.debug("nic '%s' configuration: %s", if_name, ncfg)

    if dns_servers:
        LOG.debug("added dns servers: %s", dns_servers)
        nic_configs.append({'type': 'nameserver', 'address': dns_servers})

    return {'version': 1, 'config': nic_configs}


def read_metadata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(url, timeout=timeout,
                                  sec_between=sec_between, retries=retries)
    if not response.ok():
        raise RuntimeError("unable to read metadata at %s" % url)
    return json.loads(response.contents.decode())


def read_sysinfo():
    # DigitalOcean embeds vendor ID and instance/droplet_id in the
    # SMBIOS information

    # Detect if we are on DigitalOcean and return the Droplet's ID
    vendor_name = util.read_dmi_data("system-manufacturer")
    if vendor_name != "DigitalOcean":
        return (False, None)

    droplet_id = util.read_dmi_data("system-serial-number")
    if droplet_id:
        LOG.debug("system identified via SMBIOS as DigitalOcean Droplet: %s",
                  droplet_id)
    else:
        msg = ("system identified via SMBIOS as a DigitalOcean "
               "Droplet, but did not provide an ID. Please file a "
               "support ticket at: "
               "https://cloud.digitalocean.com/support/tickets/new")
        LOG.critical(msg)
        raise RuntimeError(msg)

    return (True, droplet_id)

# vi: ts=4 expandtab
