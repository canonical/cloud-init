"""Networking-related tests."""

import contextlib
import json

import pytest
import yaml

from cloudinit.subp import subp
from tests.integration_tests import random_mac_address
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import (
    CURRENT_RELEASE,
    IS_UBUNTU,
    JAMMY,
    MANTIC,
    NOBLE,
)
from tests.integration_tests.util import verify_clean_log

# Older Ubuntu series didn't read cloud-init.* config keys
LXD_NETWORK_CONFIG_KEY = (
    "user.network-config"
    if CURRENT_RELEASE < JAMMY
    else "cloud-init.network-config"
)


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
        if CURRENT_RELEASE < MANTIC:
            assert (
                "No netplan python module. Fallback to write"
                " /etc/netplan/50-cloud-init.yaml" in log
            )
        else:
            assert "Rendered netplan config using netplan python API" in log
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
      match:
        macaddress: {mac_addr}
"""

BAD_NETWORK_V2 = """\
version: 2
ethernets:
  eth0:
    dhcp4: badval
    match:
      {match_condition}
"""


@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires custom networking provided by LXD",
)
@pytest.mark.parametrize(
    "net_config",
    (
        pytest.param(NET_V1_CONFIG, id="v1"),
        pytest.param(NET_V2_MATCH_CONFIG, id="v2"),
    ),
)
def test_netplan_rendering(
    net_config, session_cloud: IntegrationCloud, setup_image
):
    mac_addr = random_mac_address()
    launch_kwargs = {
        "config_dict": {
            LXD_NETWORK_CONFIG_KEY: net_config.format(mac_addr=mac_addr),
            "volatile.eth0.hwaddr": mac_addr,
        },
    }
    expected = yaml.safe_load(EXPECTED_NET_CONFIG)
    expected["network"]["ethernets"]["eth0"]["match"] = {
        "macaddress": mac_addr
    }
    with session_cloud.launch(launch_kwargs=launch_kwargs) as client:
        result = client.execute("cat /etc/netplan/50-cloud-init.yaml")
        if CURRENT_RELEASE < MANTIC:
            assert result.stdout.startswith(EXPECTED_NETPLAN_HEADER)
        else:
            assert EXPECTED_NETPLAN_HEADER not in result.stdout
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
    # TODO: This test takes a lot more time than it needs to.
    # The default launch wait will wait until cloud-init done, but the
    # init network stage will wait 2 minutes for network timeout.
    # We could set wait=False and do our own waiting, but there's also the
    # issue of `execute_via_ssh=False` on pycloudlib means we `sudo -u ubuntu`
    # the exec commands, but the ubuntu user won't exist until
    # # after the init network stage runs.
    mac_addr = random_mac_address()
    launch_kwargs = {
        "execute_via_ssh": False,
        "config_dict": {
            LXD_NETWORK_CONFIG_KEY: net_config.format(mac_addr=mac_addr),
            "volatile.eth0.hwaddr": mac_addr,
        },
    }
    expected = yaml.safe_load(EXPECTED_NET_CONFIG)
    expected["network"]["ethernets"]["eth0"]["match"] = {}
    expected["network"]["ethernets"]["eth0"]["match"]["macaddress"] = mac_addr
    with session_cloud.launch(launch_kwargs=launch_kwargs) as client:
        result = client.execute("cloud-init status --format=json")
        if CURRENT_RELEASE < NOBLE:
            assert result.ok
            assert result.return_code == 0  # Stable release still exit 0
        else:
            assert result.failed
            assert result.return_code == 2  # Warnings exit 2 after 23.4
        assert (
            'eth01234567890123\\" is wrong: \\"name\\" not a valid ifname'
            in result.stdout
        )
        result = client.execute("cloud-init schema --system")
        assert "Invalid network-config " in result.stdout


@pytest.mark.skipif(
    not IS_UBUNTU, reason="Dependent on netplan API availability on Ubuntu"
)
@pytest.mark.skipif(
    PLATFORM not in ("lxd_vm", "lxd_container"),
    reason="Test requires lxc exec feature due to broken network config",
)
def test_invalid_network_v2_netplan(
    session_cloud: IntegrationCloud, setup_image
):
    mac_addr = random_mac_address()

    if PLATFORM == "lxd_vm":
        config_dict = {
            LXD_NETWORK_CONFIG_KEY: BAD_NETWORK_V2.format(
                match_condition=f"macaddress: {mac_addr}"
            ),
            "volatile.eth0.hwaddr": mac_addr,
        }
    else:
        config_dict = {
            LXD_NETWORK_CONFIG_KEY: BAD_NETWORK_V2.format(
                match_condition="name: eth0"
            )
        }

    with session_cloud.launch(
        launch_kwargs={
            "execute_via_ssh": False,
            "config_dict": config_dict,
        }
    ) as client:
        # Netplan python API only available on MANTIC and later
        if CURRENT_RELEASE < MANTIC:
            assert (
                "Skipping netplan schema validation. No netplan API available"
            ) in client.read_from_file("/var/log/cloud-init.log")
            assert (
                "Skipping network-config schema validation for version: 2."
                " No netplan API available."
            ) in client.execute("cloud-init schema --system")
        else:
            assert (
                "network-config failed schema validation! You may run "
                "'sudo cloud-init schema --system' to check the details."
            ) in client.execute("cloud-init status --format=json")
            assert (
                "Invalid network-config /var/lib/cloud/instances/"
                in client.execute("cloud-init schema --system")
            )
            assert (
                "# E1: Invalid netplan schema. Error in network definition:"
                " invalid boolean value 'badval"
            ) in client.execute("cloud-init schema --system --annotate")


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_ec2_multi_nic_reboot(setup_image, session_cloud: IntegrationCloud):
    """Tests that additional secondary NICs and secondary IPs on them are
    routable from non-local networks after a reboot event when network updates
    are configured on every boot."""
    with session_cloud.launch(launch_kwargs={}, user_data=USER_DATA) as client:
        # Add secondary NIC with two private and public ips
        client.instance.add_network_interface(
            ipv4_address_count=2, ipv4_public_ip_count=2
        )

        public_ips = client.instance.public_ips
        assert len(public_ips) == 3, (
            "Expected 3 public ips, one from the primary nic and 2 from the"
            " secondary one"
        )

        # Reboot to update network config
        client.execute("cloud-init clean --logs")
        client.restart()

        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)

        # SSH over primary and secondary NIC works
        for ip in public_ips:
            subp("nc -w 5 -zv " + ip + " 22", shell=True)


@pytest.mark.adhoc  # costly instance not available in all regions / azs
@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_ec2_multi_network_cards(setup_image, session_cloud: IntegrationCloud):
    """
    Tests that with an interface type with multiple network cards (non unique
    device indexes).

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-eni.html
    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/p5-efa.html
    """
    ec2 = session_cloud.cloud_instance.client

    vpc = session_cloud.cloud_instance.get_or_create_vpc(
        name="ec2-cloud-init-integration"
    )
    [subnet_id] = [s.id for s in vpc.vpc.subnets.all()]
    security_group_ids = [sg.id for sg in vpc.vpc.security_groups.all()]

    launch_kwargs = {
        "InstanceType": "p5.48xlarge",
        "NetworkInterfaces": [
            {
                "NetworkCardIndex": 0,
                "DeviceIndex": 0,
                "InterfaceType": "efa",
                "DeleteOnTermination": True,
                "Groups": security_group_ids,
                "SubnetId": subnet_id,
            },
            {
                "NetworkCardIndex": 1,
                "DeviceIndex": 1,
                "InterfaceType": "efa",
                "DeleteOnTermination": True,
                "Groups": security_group_ids,
                "SubnetId": subnet_id,
            },
            {
                "NetworkCardIndex": 2,
                "DeviceIndex": 1,
                "InterfaceType": "efa",
                "DeleteOnTermination": True,
                "Groups": security_group_ids,
                "SubnetId": subnet_id,
            },
        ],
    }
    # Instances with this network setups do not get a public ip.
    # Do not wait until we associate one to the primary interface so that we
    # can interact with it.
    with session_cloud.launch(
        launch_kwargs=launch_kwargs,
        user_data=USER_DATA,
        enable_ipv6=False,
        wait=False,
    ) as client:
        client.instance._instance.wait_until_running(
            Filters=[
                {
                    "Name": "instance-id",
                    "Values": [client.instance.id],
                }
            ]
        )

        network_interfaces = iter(
            ec2.describe_network_interfaces(
                Filters=[
                    {
                        "Name": "attachment.instance-id",
                        "Values": [client.instance.id],
                    }
                ]
            )["NetworkInterfaces"]
        )
        nic_id_0 = next(network_interfaces)["NetworkInterfaceId"]

        try:
            allocation_0 = ec2.allocate_address(Domain="vpc")
            association_0 = ec2.associate_address(
                AllocationId=allocation_0["AllocationId"],
                NetworkInterfaceId=nic_id_0,
            )
            assert association_0["ResponseMetadata"]["HTTPStatusCode"] == 200

            result = client.execute(
                "cloud-init query ds.meta-data.network.interfaces.macs"
            )
            assert result.ok, result.stderr
            for _macs, net_metadata in json.load(result.stdout):
                assert "network-card" in net_metadata

            nic_id_1 = next(network_interfaces)["NetworkInterfaceId"]
            allocation_1 = ec2.allocate_address(Domain="vpc")
            association_1 = ec2.associate_address(
                AllocationId=allocation_1["AllocationId"],
                NetworkInterfaceId=nic_id_1,
            )
            assert association_1["ResponseMetadata"]["HTTPStatusCode"] == 200

            nic_id_2 = next(network_interfaces)["NetworkInterfaceId"]
            allocation_2 = ec2.allocate_address(Domain="vpc")
            association_2 = ec2.associate_address(
                AllocationId=allocation_2["AllocationId"],
                NetworkInterfaceId=nic_id_2,
            )
            assert association_2["ResponseMetadata"]["HTTPStatusCode"] == 200

            # Reboot to update network config
            client.execute("cloud-init clean --logs")
            client.restart()

            log_content = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log_content)

            # SSH over secondary NICs works
            subp("nc -w 5 -zv " + allocation_1["PublicIp"] + " 22", shell=True)
            subp("nc -w 5 -zv " + allocation_2["PublicIp"] + " 22", shell=True)
        finally:
            with contextlib.suppress(Exception):
                ec2.disassociate_address(
                    AssociationId=association_0["AssociationId"]
                )
            with contextlib.suppress(Exception):
                ec2.release_address(AllocationId=allocation_0["AllocationId"])
            with contextlib.suppress(Exception):
                ec2.disassociate_address(
                    AssociationId=association_1["AssociationId"]
                )
            with contextlib.suppress(Exception):
                ec2.release_address(AllocationId=allocation_1["AllocationId"])
            with contextlib.suppress(Exception):
                ec2.disassociate_address(
                    AssociationId=association_2["AssociationId"]
                )
            with contextlib.suppress(Exception):
                ec2.release_address(AllocationId=allocation_2["AllocationId"])
