"""Integration test for gh-626.

Ensure if wakeonlan is specified in the network config that it is rendered
in the /etc/network/interfaces or netplan config.
"""
import pytest
import yaml

from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.integration_settings import PLATFORM

MAC_ADDRESS = random_mac_address()
NETWORK_CONFIG = """\
version: 2
ethernets:
  eth0:
    dhcp4: true
    wakeonlan: true
    match:
      {match_clause}
"""

# On netplan 0.106 and above, netplan emits mac address matches as
# PermanentMACAdddress on networkd systems. This match clause will
# not match LXD's veth devices which results in no IPv4 address
# being allocated via DHCP. As a result, we match container by NIC name.
# LP: #2022947 represents this netplan behavior
NETWORK_CONFIG_CONTAINER = NETWORK_CONFIG.format(match_clause="name: eth0")

# Match LXD VM by MAC just to assert plumbing is working by MAC
NETWORK_CONFIG_VM = NETWORK_CONFIG.format(
    match_clause=f"macaddress: {MAC_ADDRESS}"
)

EXPECTED_ENI_END = """\
iface eth0 inet dhcp
    ethernet-wol g"""


@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason="Test requires custom networking provided by LXD",
)
def test_wakeonlan(session_cloud: IntegrationCloud):
    if PLATFORM == "lxd_vm":
        config_dict = {
            "user.network-config": NETWORK_CONFIG_VM,
            "volatile.eth0.hwaddr": MAC_ADDRESS,
        }
    else:
        config_dict = {"user.network-config": NETWORK_CONFIG_CONTAINER}
    with session_cloud.launch(
        launch_kwargs={
            "config_dict": config_dict,
        }
    ) as client:
        netplan_cfg = client.execute("cat /etc/netplan/50-cloud-init.yaml")
        netplan_yaml = yaml.safe_load(netplan_cfg)
        assert "wakeonlan" in netplan_yaml["network"]["ethernets"]["eth0"]
        assert (
            netplan_yaml["network"]["ethernets"]["eth0"]["wakeonlan"] is True
        )
