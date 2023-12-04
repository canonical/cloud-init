"""Integration test for LP: #1898997

cloud-init was incorrectly excluding Open vSwitch bridge members from its list
of interfaces.  This meant that instances which had only one interface which
was in an Open vSwitch bridge would not boot correctly: cloud-init would not
find the expected physical interfaces, so would not apply network config.

This test checks that cloud-init believes it has successfully applied the
network configuration, and confirms that the bridge can be used to ping the
default gateway.
"""
import pytest

from tests.integration_tests import random_mac_address
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import verify_clean_log

MAC_ADDRESS = random_mac_address()


NETWORK_CONFIG = """\
bridges:
        ovs-br:
            dhcp4: true
            interfaces:
            - enp5s0
            macaddress: 52:54:00:d9:08:1c
            mtu: 1500
            openvswitch: {{}}
ethernets:
    enp5s0:
      mtu: 1500
      set-name: enp5s0
      match:
          macaddress: {}
version: 2
""".format(
    MAC_ADDRESS
)


@pytest.mark.lxd_config_dict(
    {
        "user.network-config": NETWORK_CONFIG,
        "volatile.eth0.hwaddr": MAC_ADDRESS,
    }
)
@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires custom networking provided by LXD",
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL, reason="Tested on Focal and above"
)
@pytest.mark.lxd_use_exec
@pytest.mark.skip(
    reason="Network online race. GH: #4350, GH: #4451, LP: #2036968"
)
class TestInterfaceListingWithOpenvSwitch:
    def test_ovs_member_interfaces_not_excluded(self, client):
        # We need to install openvswitch for our provided network configuration
        # to apply (on next boot), so DHCP on our default interface to fetch it
        client.execute("dhclient enp5s0")
        client.execute("apt update -qqy")
        client.execute("apt-get install -qqy openvswitch-switch")

        # Now our networking config should successfully apply on a clean reboot
        client.execute("cloud-init clean --logs")
        client.restart()

        cloudinit_output = client.read_from_file("/var/log/cloud-init.log")

        # Confirm that the network configuration was applied successfully
        verify_clean_log(cloudinit_output)
        # Confirm that the applied network config created the OVS bridge
        assert "ovs-br" in client.execute("ip addr")

        # Test that we can ping our gateway using our bridge
        gateway = client.execute(
            "ip -4 route show default | awk '{ print $3 }'"
        )
        ping_result = client.execute(
            "ping -c 1 -W 1 -I ovs-br {}".format(gateway)
        )
        assert ping_result.ok
