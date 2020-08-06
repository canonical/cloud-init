# Author: Alexander Birkner <alexander.birkner@g-portal.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import log as logging
from cloudinit import net as cloudnet
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)


def load_metadata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(url, timeout=timeout,
                                  sec_between=sec_between, retries=retries)
    if not response.ok():
        raise RuntimeError("unable to read metadata at %s" % url)
    return util.load_json(response.contents.decode())


def convert_network_configuration(config, dns_servers, routes):
    """Convert the GPortal Network config into Cloud-Init's netconfig (v1) format.
       See: https://cloudinit.readthedocs.io/en/latest/topics/network-config-format-v1.html

       Example JSON:
        {'public': [
              {'mac': '40:9a:4c:8d:96:77',
               'ipv4': {'gateway': '176.57.186.5',
                        'netmask': '255.255.255.0',
                        'address': '176.57.186.1'},
               'type': 'public'
           ]
        }
    """  # noqa: E501

    def _convert_subnet(cfg):
        subpart = {'type': 'static',
                   'control': 'auto',
                   'address': cfg.get('address'),
                   'gateway': cfg.get('gateway'),
                   'netmask': cfg.get('netmask')}

        return subpart

    nic_configs = []

    # Returns a map where the mac address is the key
    # and the value is the interface name (e.g. eno3)
    macs_to_nics = cloudnet.get_interfaces_by_mac()
    LOG.debug("nic mapping: %s", macs_to_nics)

    for n in config:
        nic = config[n][0]

        mac_address = nic.get('mac')
        if mac_address not in macs_to_nics:
            raise RuntimeError("Did not find network interface on system "
                               "with mac '%s'. Cannot apply configuration: %s"
                               % (mac_address, nic))

        if_name = macs_to_nics.get(mac_address)
        nic_type = nic.get('type', 'unknown')

        ncfg = {'type': 'physical',
                'mac_address': mac_address,
                'name': if_name}

        subnets = []
        raw_subnet = nic.get('ipv4', None)
        if not raw_subnet:
            continue

        # Convert subnet to ncfg subnet
        sub_part = _convert_subnet(raw_subnet)

        # Only the public interface has a gateway address
        if nic_type != "public":
            del sub_part['gateway']

        subnets.append(sub_part)

        ncfg['subnets'] = subnets
        nic_configs.append(ncfg)
        LOG.debug("nic '%s' configuration: %s", if_name, ncfg)

    if dns_servers:
        LOG.debug("added dns servers: %s", dns_servers)
        nic_configs.append({'type': 'nameserver', 'address': dns_servers})

    if routes is not None:
        for route in routes:
            nic_configs.append({
                'type': 'route',
                'destination': route['destination'],
                'gateway': route['gateway'],
                'metric': route['metric'],
            })

    return {'version': 1, 'config': nic_configs}
