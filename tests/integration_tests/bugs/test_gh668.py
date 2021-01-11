"""Integration test for gh-668.

Ensure that static route to host is working correctly.
"""

import pytest

from tests.integration_tests.instances import IntegrationInstance


DESTINATION_IP = "172.16.0.10"
GATEWAY_IP = "10.0.0.100"

NETWORK_CONFIG = """\
version: 2
ethernets:
  eth0:
    addresses: [10.0.0.10/8]
    dhcp4: false
    routes:
    - to: {}/32
      via: {}
""".format(DESTINATION_IP, GATEWAY_IP)

EXPECTED_ROUTE = "{} via {}".format(DESTINATION_IP, GATEWAY_IP)


@pytest.mark.sru_2020_11
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.lxd_config_dict({
    "user.network-config": NETWORK_CONFIG,
})
def test_eni_static_route_to_host(client: IntegrationInstance):
    route = client.execute("ip route | grep {}".format(DESTINATION_IP))
    assert route.startswith(EXPECTED_ROUTE)
