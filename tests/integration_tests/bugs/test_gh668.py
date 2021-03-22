"""Integration test for gh-668.

Ensure that static route to host is working correctly.
The original problem is specific to the ENI renderer but that test is suitable
for all network configuration outputs.
"""

import pytest

from tests.integration_tests import random_mac_address
from tests.integration_tests.instances import IntegrationInstance


DESTINATION_IP = "172.16.0.10"
GATEWAY_IP = "10.0.0.100"
MAC_ADDRESS = random_mac_address()

NETWORK_CONFIG = """\
version: 2
ethernets:
  eth0:
    addresses: [10.0.0.10/8]
    dhcp4: false
    routes:
    - to: {}/32
      via: {}
    match:
      macaddress: {}
""".format(DESTINATION_IP, GATEWAY_IP, MAC_ADDRESS)

EXPECTED_ROUTE = "{} via {}".format(DESTINATION_IP, GATEWAY_IP)


@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.lxd_config_dict({
    "user.network-config": NETWORK_CONFIG,
    "volatile.eth0.hwaddr": MAC_ADDRESS,
})
@pytest.mark.lxd_use_exec
def test_static_route_to_host(client: IntegrationInstance):
    route = client.execute("ip route | grep {}".format(DESTINATION_IP))
    assert route.startswith(EXPECTED_ROUTE)
