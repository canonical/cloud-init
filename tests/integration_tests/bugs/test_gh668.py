"""Integration test for gh-668.

Ensure that static route to host is working correctly.
The original problem is specific to the ENI renderer but that test is suitable
for all network configuration outputs.
"""

import pytest

from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.integration_settings import PLATFORM

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
""".format(
    DESTINATION_IP, GATEWAY_IP
)

EXPECTED_ROUTE = "{} via {}".format(DESTINATION_IP, GATEWAY_IP)


NETWORK_CONFIG_VM = f"""\
{NETWORK_CONFIG}
    match:
      macaddress: {MAC_ADDRESS}
"""

# On netplan 0.106 and above, netplan emits MAC address matches as
# PermanentMACAdddress= on networkd systems. This match clause will
# not match LXD's veth devices which results in no routes being brought up.
# As a result, we match container by NIC name. Leave lxd_vm as MAC match.
# LP: #2022947 represents this netplan behavior
NETWORK_CONFIG_CONTAINER = f"""\
{NETWORK_CONFIG}
    match:
      name: eth0
"""


@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason="Test requires custom networking provided by LXD",
)
def test_static_route_to_host(session_cloud: IntegrationCloud):
    if PLATFORM == "lxd_vm":
        config_dict = {
            "user.network-config": NETWORK_CONFIG_VM,
            "volatile.eth0.hwaddr": MAC_ADDRESS,
        }
    else:
        config_dict = {"user.network-config": NETWORK_CONFIG_CONTAINER}
    with session_cloud.launch(
        launch_kwargs={
            "execute_via_ssh": False,
            "config_dict": config_dict,
        }
    ) as client:
        route = client.execute("ip route | grep {}".format(DESTINATION_IP))
        assert route.startswith(EXPECTED_ROUTE)
