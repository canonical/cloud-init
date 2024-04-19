"""Integration tests for networkv2 schema validation"""

import pytest
import yaml

from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.integration_settings import PLATFORM

MAC_ADDRESS = random_mac_address()

# Valid networkv2
NETWORK_V2_VALID_CONFIG = """
network:
  version: 2
  ethernets:
    id0:
      match:
        {match_clause}
      wakeonlan: true
      dhcp4: true
      dhcp4-overrides:
        route-metric: 99
      dhcp6-overrides:
        route-metric: 99
"""

# Invalid networkv2
NETWORK_V2_INVALID_CONFIG = """
network:
  version: 2
  config:
  - type: physical
    name: eth0
    subnets:
      - type: dhcp
"""

@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason="Test requires custom networking provided by LXD",
)
def test_valid_networkv2config(session_cloud: IntegrationCloud):
    config_dict = {}
    if PLATFORM == "lxd_vm":
        network_config_vm = NETWORK_V2_VALID_CONFIG.format(
            match_clause=f"macaddress: {MAC_ADDRESS}"
        )
        config_dict = {
            "user.network-config": network_config_vm,
            "volatile.eth0.hwaddr": MAC_ADDRESS,
        }
    else:
        network_config_container = NETWORK_V2_VALID_CONFIG.format(
            match_clause="name: eth0"
        )
        config_dict = {"user.network-config": network_config_container}

    with session_cloud.launch(
        launch_kwargs={
            "config_dict": config_dict,
        }
    ) as client:
        schema_validation = client.execute("cloud-init schema --system")
        assert "Valid schema network-config" in schema_validation
        netplan_cfg = client.execute("cat /etc/netplan/50-cloud-init.yaml")
        netplan_yaml = yaml.safe_load(netplan_cfg)
        assert "wakeonlan" in netplan_yaml["network"]["ethernets"]["id0"]
        assert (
            netplan_yaml["network"]["ethernets"]["id0"]["wakeonlan"] is True
        )

@pytest.mark.skipif(
    PLATFORM not in ["lxd_container"],
    reason="Test requires custom networking provided by LXD",
)
def test_invalid_networkv2config(session_cloud: IntegrationCloud):
    network_config_container = NETWORK_V2_INVALID_CONFIG.format(
        match_clause="name: eth0"
    )
    config_dict = {"user.network-config": network_config_container}

    with session_cloud.launch(
        launch_kwargs={
            "config_dict": config_dict,
        }
    ) as client:
        schema_validation = client.execute("cloud-init schema --system")
        assert "Invalid network-config" in schema_validation

