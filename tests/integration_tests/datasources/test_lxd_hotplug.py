import json

import pytest

from cloudinit import safeyaml
from cloudinit.subp import subp
from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
updates:
  network:
    when: ["hotplug"]
"""

UPDATED_NETWORK_CONFIG = """\
version: 2
ethernets:
    eth0:
        dhcp4: true
    eth2:
        dhcp4: true
"""


@retry()
def ensure_hotplug_exited(client):
    assert "cloud-init" not in client.execute("ps -A")


def get_parent_network():
    lxd_network = json.loads(
        subp("lxc network list --format json".split()).stdout
    )
    managed_networks = [n for n in lxd_network if n["managed"] is True]
    return managed_networks[0]["name"] if managed_networks else "lxdbr0"


@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.user_data(USER_DATA)
class TestLxdHotplug:
    @pytest.fixture(autouse=True, scope="class")
    def class_teardown(self, class_client: IntegrationInstance):
        # We need a teardown here because on IntegrationInstance teardown,
        # if KEEP_INSTANCE=True, we grab the instance IP for logging, but
        # we're currently running into
        # https://github.com/canonical/pycloudlib/issues/220 .
        # Once that issue is fixed, we can remove this teardown
        yield
        name = class_client.instance.name
        subp(f"lxc config device remove {name} eth1".split())
        subp(f"lxc config device remove {name} eth2".split())

    def test_no_network_change_default(
        self, class_client: IntegrationInstance
    ):
        client = class_client
        assert "eth1" not in client.execute("ip address")
        pre_netplan = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        assert subp(
            f"lxc config device add {client.instance.name} eth1 nic name=eth1 "
            f"nictype=bridged parent={get_parent_network()}".split()
        )
        ensure_hotplug_exited(client)
        post_netplan = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        assert pre_netplan == post_netplan
        ip_info = json.loads(client.execute("ip --json address"))
        eth1s = [i for i in ip_info if i["ifname"] == "eth1"]
        assert len(eth1s) == 1
        assert eth1s[0]["operstate"] == "DOWN"

    def test_network_config_applied(self, class_client: IntegrationInstance):
        client = class_client
        assert "eth2" not in client.execute("ip address")
        pre_netplan = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        assert "eth2" not in pre_netplan
        assert subp(
            [
                "lxc",
                "config",
                "set",
                client.instance.name,
                f"cloud-init.network-config={UPDATED_NETWORK_CONFIG}",
            ]
        )
        assert (
            client.read_from_file("/etc/netplan/50-cloud-init.yaml")
            == pre_netplan
        )
        assert subp(
            f"lxc config device add {client.instance.name} eth2 nic name=eth2 "
            f"nictype=bridged parent={get_parent_network()}".split()
        )
        ensure_hotplug_exited(client)
        post_netplan = safeyaml.load(
            client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        )
        expected_netplan = safeyaml.load(UPDATED_NETWORK_CONFIG)
        expected_netplan = {"network": expected_netplan}
        assert post_netplan == expected_netplan, client.read_from_file(
            "/var/log/cloud-init.log"
        )
        ip_info = json.loads(client.execute("ip --json address"))
        eth2s = [i for i in ip_info if i["ifname"] == "eth2"]
        assert len(eth2s) == 1
        assert eth2s[0]["operstate"] == "UP"
