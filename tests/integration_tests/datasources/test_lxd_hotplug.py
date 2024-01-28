import json

import pytest

from cloudinit import safeyaml
from cloudinit.subp import subp
from cloudinit.util import is_true
from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, JAMMY
from tests.integration_tests.util import (
    get_feature_flag_value,
    lxd_has_nocloud,
)

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


def get_parent_network(instance_name: str):
    lxd_network = json.loads(
        subp("lxc network list --format json".split()).stdout
    )
    for net in lxd_network:
        if net["type"] == "bridge" and net["managed"]:
            if f"/1.0/instances/{instance_name}" in net.get("used_by", []):
                return net["name"]
    return "lxdbr0"


def _prefer_lxd_datasource_over_nocloud(client: IntegrationInstance):
    """For hotplug support we need LXD datasource detected instead of NoCloud

    Bionic and Focal still deliver nocloud-net seed files so override it
    with /etc/cloud/cloud.cfg.d/99-detect-lxd-first.cfg
    """
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-detect-lxd-first.cfg",
        "datasource_list: [LXD, NoCloud]\n",
    )
    client.execute("cloud-init clean --logs")
    client.restart()


# TODO: Once LXD adds MACs to the devices endpoint, support LXD VMs here
# Currently the names are too unpredictable to be worth testing on VMs.
@pytest.mark.user_data(USER_DATA)
@pytest.mark.skipif(
    PLATFORM != "lxd_container",
    reason="Test is LXD specific",
)
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
        subp("lxc network delete ci-test-br-eth1".split())
        subp("lxc network delete ci-test-br-eth2".split())

    def test_no_network_change_default(
        self, class_client: IntegrationInstance
    ):
        client = class_client
        if lxd_has_nocloud(client):
            _prefer_lxd_datasource_over_nocloud(client)
        assert "eth1" not in client.execute("ip address")
        pre_netplan = client.read_from_file("/etc/netplan/50-cloud-init.yaml")

        networks = subp("lxc network list".split())
        if "ci-test-br-eth1" not in networks.stdout:
            subp(
                "lxc network create ci-test-br-eth1 --type=bridge "
                "ipv4.address=10.10.41.1/24 ipv4.nat=true".split()
            )
        subp(
            f"lxc config device add {client.instance.name} eth1 nic name=eth1 "
            f"nictype=bridged parent=ci-test-br-eth1".split()
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
        if lxd_has_nocloud(client):
            _prefer_lxd_datasource_over_nocloud(client)
        assert "eth2" not in client.execute("ip address")
        pre_netplan = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        assert "eth2" not in pre_netplan
        top_key = "user" if CURRENT_RELEASE < JAMMY else "cloud-init"
        assert subp(
            [
                "lxc",
                "config",
                "set",
                client.instance.name,
                f"{top_key}.network-config={UPDATED_NETWORK_CONFIG}",
            ]
        )
        assert (
            client.read_from_file("/etc/netplan/50-cloud-init.yaml")
            == pre_netplan
        )
        networks = subp("lxc network list".split())
        if "ci-test-br-eth2" not in networks.stdout:
            assert subp(
                "lxc network create ci-test-br-eth2 --type=bridge"
                " ipv4.address=10.10.42.1/24 ipv4.nat=true".split()
            )
        assert subp(
            f"lxc config device add {client.instance.name} eth2 nic name=eth2 "
            f"nictype=bridged parent=ci-test-br-eth2".split()
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
        file_perms = class_client.execute(
            "stat -c %a /etc/netplan/50-cloud-init.yaml"
        )
        assert file_perms.ok, "Unable to check perms on 50-cloud-init.yaml"
        feature_netplan_root_only = is_true(
            get_feature_flag_value(
                class_client, "NETPLAN_CONFIG_ROOT_READ_ONLY"
            )
        )
        config_perms = "600" if feature_netplan_root_only else "644"
        assert config_perms == file_perms.stdout.strip()
        ip_info = json.loads(client.execute("ip --json address"))
        eth2s = [i for i in ip_info if i["ifname"] == "eth2"]
        assert len(eth2s) == 1
        assert eth2s[0]["operstate"] == "UP"
