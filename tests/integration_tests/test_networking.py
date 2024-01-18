"""Networking-related tests."""
import pytest
import yaml

from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM


def _add_dummy_bridge_to_netplan(client: IntegrationInstance):
    # Update netplan configuration to ensure it doesn't change on reboot
    netplan = yaml.safe_load(
        client.execute("cat /etc/netplan/50-cloud-init.yaml")
    )
    # Just a dummy bridge to do nothing
    try:
        netplan["network"]["bridges"]["dummy0"] = {"dhcp4": False}
    except KeyError:
        netplan["network"]["bridges"] = {"dummy0": {"dhcp4": False}}

    dumped_netplan = yaml.dump(netplan)
    client.write_to_file("/etc/netplan/50-cloud-init.yaml", dumped_netplan)


USER_DATA = """\
#cloud-config
updates:
  network:
    when: [boot]
"""


@pytest.mark.skipif(
    PLATFORM not in ("lxd_container", "lxd_vm"),
    reason=(
        f"{PLATFORM} could make nic changes in a reboot event invalidating"
        f" these tests."
    ),
)
@pytest.mark.user_data(USER_DATA)
class TestNetplanGenerateBehaviorOnReboot:
    def test_skip(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Applying network configuration" in log
        assert "Selected renderer 'netplan'" in log
        client.execute(
            "mv /var/log/cloud-init.log /var/log/cloud-init.log.bak"
        )
        netplan = yaml.safe_load(
            client.execute("cat /etc/netplan/50-cloud-init.yaml")
        )

        client.restart()

        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Event Allowed: scope=network EventType=boot" in log
        assert "Applying network configuration" in log
        assert "Running command ['netplan', 'generate']" not in log
        assert (
            "skipping call to `netplan generate`."
            " reason: identical netplan config"
        ) in log
        netplan_new = yaml.safe_load(
            client.execute("cat /etc/netplan/50-cloud-init.yaml")
        )
        assert netplan == netplan_new, "no changes expected in netplan config"

    def test_applied(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Applying network configuration" in log
        assert "Selected renderer 'netplan'" in log
        client.execute(
            "mv /var/log/cloud-init.log /var/log/cloud-init.log.bak"
        )
        # fake a change in the rendered network config file
        _add_dummy_bridge_to_netplan(client)
        netplan = yaml.safe_load(
            client.execute("cat /etc/netplan/50-cloud-init.yaml")
        )

        client.restart()

        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Event Allowed: scope=network EventType=boot" in log
        assert "Applying network configuration" in log
        assert (
            "skipping call to `netplan generate`."
            " reason: identical netplan config"
        ) not in log
        assert "Running command ['netplan', 'generate']" in log
        netplan_new = yaml.safe_load(
            client.execute("cat /etc/netplan/50-cloud-init.yaml")
        )
        assert netplan != netplan_new, "changes expected in netplan config"


NET_V1_CONFIG = """
config:
- name: eth0
  type: physical
  mac_address: '{mac_addr}'
  subnets:
  - control: auto
    type: dhcp
version: 1
"""


NET_V2_MATCH_CONFIG = """
version: 2
ethernets:
  eth0:
      dhcp4: true
      match:
        macaddress: {mac_addr}
      set-name: eth0
"""

EXPECTED_NETPLAN_HEADER = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}"""

EXPECTED_NET_CONFIG = """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      set-name: eth0
"""


@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires custom networking provided by LXD",
)
@pytest.mark.parametrize("net_config", (NET_V1_CONFIG, NET_V2_MATCH_CONFIG))
def test_netplan_rendering(
    net_config, session_cloud: IntegrationCloud, setup_image
):
    mac_addr = random_mac_address()
    launch_kwargs = {
        "config_dict": {
            "cloud-init.network-config": net_config.format(mac_addr=mac_addr),
            "volatile.eth0.hwaddr": mac_addr,
        },
    }
    expected = yaml.safe_load(EXPECTED_NET_CONFIG)
    expected["network"]["ethernets"]["eth0"]["match"]["macaddress"] = mac_addr
    with session_cloud.launch(launch_kwargs=launch_kwargs) as client:
        result = client.execute("cat /etc/netplan/50-cloud-init.yaml")
        assert result.stdout.startswith(EXPECTED_NETPLAN_HEADER)
        assert expected == yaml.safe_load(result.stdout)


NET_V1_NAME_TOO_LONG = """\
config:
- name: eth01234567890123
  type: physical
  mac_address: '{mac_addr}'
  subnets:
  - control: auto
    type: dhcp
version: 1
"""


@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires custom networking provided by LXD",
)
@pytest.mark.parametrize("net_config", (NET_V1_NAME_TOO_LONG,))
def test_schema_warnings(
    net_config, session_cloud: IntegrationCloud, setup_image
):
    mac_addr = random_mac_address()
    launch_kwargs = {
        "execute_via_ssh": False,
        "config_dict": {
            "cloud-init.network-config": net_config.format(mac_addr=mac_addr),
            "volatile.eth0.hwaddr": mac_addr,
        },
    }
    expected = yaml.safe_load(EXPECTED_NET_CONFIG)
    expected["network"]["ethernets"]["eth0"]["match"]["macaddress"] = mac_addr
    with session_cloud.launch(launch_kwargs=launch_kwargs) as client:
        result = client.execute("cloud-init status --format=json")
        assert result.failed
        assert result.return_code == 2  # Warning
        assert (
            'eth01234567890123\\" is wrong: \\"name\\" not a valid ifname'
            in result.stdout
        )
        result = client.execute("cloud-init schema --system")
        assert "Invalid network-config" in result.stdout
