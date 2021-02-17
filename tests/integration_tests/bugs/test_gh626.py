"""Integration test for gh-626.

Ensure if wakeonlan is specified in the network config that it is rendered
in the /etc/network/interfaces or netplan config.
"""

import pytest
import yaml

from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance


MAC_ADDRESS = random_mac_address()
NETWORK_CONFIG = """\
version: 2
ethernets:
  eth0:
    dhcp4: true
    wakeonlan: true
    match:
      macaddress: {}
""".format(MAC_ADDRESS)

EXPECTED_ENI_END = """\
iface eth0 inet dhcp
    ethernet-wol g"""


@pytest.mark.sru_2020_11
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.lxd_config_dict({
    'user.network-config': NETWORK_CONFIG,
    "volatile.eth0.hwaddr": MAC_ADDRESS,
})
def test_wakeonlan(client: IntegrationInstance):
    if ImageSpecification.from_os_image().release == 'xenial':
        eni = client.execute('cat /etc/network/interfaces.d/50-cloud-init.cfg')
        assert eni.endswith(EXPECTED_ENI_END)
        return

    netplan_cfg = client.execute('cat /etc/netplan/50-cloud-init.yaml')
    netplan_yaml = yaml.safe_load(netplan_cfg)
    assert 'wakeonlan' in netplan_yaml['network']['ethernets']['eth0']
    assert netplan_yaml['network']['ethernets']['eth0']['wakeonlan'] is True
