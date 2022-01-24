"""Integration test for LP: #1912844

cloud-init should ignore OVS-internal interfaces when performing its own
interface determination: these interfaces are handled fully by OVS, so
cloud-init should never need to touch them.

This test is a semi-synthetic reproducer for the bug.  It uses a similar
network configuration, tweaked slightly to DHCP in a way that will succeed even
on "failed" boots.  The exact bug doesn't reproduce with the NoCloud
datasource, because it runs at init-local time (whereas the MAAS datasource,
from the report, runs only at init (network) time): this means that the
networking code runs before OVS creates its interfaces (which happens after
init-local but, of course, before networking is up), and so doesn't generate
the traceback that they cause.  We work around this by calling
``get_interfaces_by_mac` directly in the test code.
"""
import pytest

from tests.integration_tests import random_mac_address

MAC_ADDRESS = random_mac_address()

NETWORK_CONFIG = """\
bonds:
    bond0:
        interfaces:
            - enp5s0
        macaddress: {0}
        mtu: 1500
bridges:
        ovs-br:
            interfaces:
            - bond0
            macaddress: {0}
            mtu: 1500
            openvswitch: {{}}
            dhcp4: true
ethernets:
    enp5s0:
      mtu: 1500
      set-name: enp5s0
      match:
          macaddress: {0}
version: 2
vlans:
  ovs-br.100:
    id: 100
    link: ovs-br
    mtu: 1500
  ovs-br.200:
    id: 200
    link: ovs-br
    mtu: 1500
""".format(
    MAC_ADDRESS
)


SETUP_USER_DATA = """\
#cloud-config
packages:
- openvswitch-switch
"""


@pytest.fixture
def ovs_enabled_session_cloud(session_cloud):
    """A session_cloud wrapper, to use an OVS-enabled image for tests.

    This implementation is complicated by wanting to use ``session_cloud``s
    snapshot cleanup/retention logic, to avoid having to reimplement that here.
    """
    old_snapshot_id = session_cloud.snapshot_id
    with session_cloud.launch(
        user_data=SETUP_USER_DATA,
    ) as instance:
        instance.instance.clean()
        session_cloud.snapshot_id = instance.snapshot()

    yield session_cloud

    try:
        session_cloud.delete_snapshot()
    finally:
        session_cloud.snapshot_id = old_snapshot_id


@pytest.mark.lxd_vm
def test_get_interfaces_by_mac_doesnt_traceback(ovs_enabled_session_cloud):
    """Launch our OVS-enabled image and confirm the bug doesn't reproduce."""
    launch_kwargs = {
        "config_dict": {
            "user.network-config": NETWORK_CONFIG,
            "volatile.eth0.hwaddr": MAC_ADDRESS,
        },
    }
    with ovs_enabled_session_cloud.launch(
        launch_kwargs=launch_kwargs,
    ) as client:
        result = client.execute(
            "python3 -c"
            "'from cloudinit.net import get_interfaces_by_mac;"
            "get_interfaces_by_mac()'"
        )
        assert result.ok
