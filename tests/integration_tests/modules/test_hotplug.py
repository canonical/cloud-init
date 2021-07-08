import pytest
import time
import yaml
from collections import namedtuple

from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
updates:
  network:
    when: ['hotplug']
"""

ip_addr = namedtuple('ip_addr', 'interface state ip4 ip6')


def _wait_till_hotplug_complete(client, expected_runs=1):
    for _ in range(60):
        log = client.read_from_file('/var/log/cloud-init.log')
        if log.count('Exiting hotplug handler') == expected_runs:
            return log
        time.sleep(1)
    raise Exception('Waiting for hotplug handler failed')


def _get_ip_addr(client):
    ips = []
    lines = client.execute('ip --brief addr').split('\n')
    for line in lines:
        interface, state, ip4_cidr, ip6_cidr = line.split()
        ip4 = ip4_cidr.split('/')[0]
        ip6 = ip6_cidr.split('/')[0]
        ip = ip_addr(interface, state, ip4, ip6)
        ips.append(ip)
    return ips


@pytest.mark.openstack
@pytest.mark.user_data(USER_DATA)
def test_hotplug_add_remove(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Exiting hotplug handler' not in log

    # Add new NIC
    added_ip = client.instance.add_network_interface()
    _wait_till_hotplug_complete(client)
    ips_after_add = _get_ip_addr(client)
    new_addition = [ip for ip in ips_after_add if ip.ip4 == added_ip][0]

    assert len(ips_after_add) == len(ips_before) + 1
    assert added_ip not in [ip.ip4 for ip in ips_before]
    assert added_ip in [ip.ip4 for ip in ips_after_add]
    assert new_addition.state == 'UP'

    netplan_cfg = client.read_from_file('/etc/netplan/50-cloud-init.yaml')
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface in config['network']['ethernets']

    # Remove new NIC
    client.instance.remove_network_interface(added_ip)
    _wait_till_hotplug_complete(client, expected_runs=2)
    ips_after_remove = _get_ip_addr(client)
    assert len(ips_after_remove) == len(ips_before)
    assert added_ip not in [ip.ip4 for ip in ips_after_remove]

    netplan_cfg = client.read_from_file('/etc/netplan/50-cloud-init.yaml')
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface not in config['network']['ethernets']
