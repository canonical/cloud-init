import contextlib
import time
from collections import namedtuple

import pytest
import yaml

from cloudinit.subp import subp
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
updates:
  network:
    when: ['hotplug']
"""

ip_addr = namedtuple("ip_addr", "interface state ip4 ip6")


def _wait_till_hotplug_complete(client, expected_runs=1):
    for _ in range(60):
        log = client.read_from_file("/var/log/cloud-init.log")
        if log.count("Exiting hotplug handler") == expected_runs:
            return log
        time.sleep(1)
    raise Exception("Waiting for hotplug handler failed")


def _get_ip_addr(client):
    ips = []
    lines = client.execute("ip --brief addr").split("\n")
    for line in lines:
        attributes = line.split()
        interface, state = attributes[0], attributes[1]
        ip4_cidr = attributes[2] if len(attributes) > 2 else None
        ip6_cidr = attributes[3] if len(attributes) > 3 else None
        ip4 = ip4_cidr.split("/")[0] if ip4_cidr else None
        ip6 = ip6_cidr.split("/")[0] if ip6_cidr else None
        ip = ip_addr(interface, state, ip4, ip6)
        ips.append(ip)
    return ips


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        f"Test was written for {PLATFORM} but can likely run on "
        "other platforms."
    ),
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL,
    reason="Openstack network metadata support was added in focal.",
)
@pytest.mark.user_data(USER_DATA)
def test_hotplug_add_remove(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).ok

    # Add new NIC
    added_ip = client.instance.add_network_interface()
    _wait_till_hotplug_complete(client, expected_runs=1)
    ips_after_add = _get_ip_addr(client)
    new_addition = [ip for ip in ips_after_add if ip.ip4 == added_ip][0]

    assert len(ips_after_add) == len(ips_before) + 1
    assert added_ip not in [ip.ip4 for ip in ips_before]
    assert added_ip in [ip.ip4 for ip in ips_after_add]
    assert new_addition.state == "UP"

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface in config["network"]["ethernets"]

    # Remove new NIC
    client.instance.remove_network_interface(added_ip)
    _wait_till_hotplug_complete(client, expected_runs=2)
    ips_after_remove = _get_ip_addr(client)
    assert len(ips_after_remove) == len(ips_before)
    assert added_ip not in [ip.ip4 for ip in ips_after_remove]

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface not in config["network"]["ethernets"]

    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        f"Test was written for {PLATFORM} but can likely run on "
        "other platforms."
    ),
)
def test_no_hotplug_in_userdata(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).failed

    # Add new NIC
    client.instance.add_network_interface()
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "hotplug-hook" not in log

    ips_after_add = _get_ip_addr(client)
    if len(ips_after_add) == len(ips_before) + 1:
        # We can see the device, but it should not have been brought up
        new_ip = [ip for ip in ips_after_add if ip not in ips_before][0]
        assert new_ip.state == "DOWN"
    else:
        assert len(ips_after_add) == len(ips_before)

    assert "disabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_multi_nic_hotplug(setup_image, session_cloud: IntegrationCloud):
    """Tests that additional secondary NICs are routable from non-local
    networks after the hotplug hook is executed when network updates
    are configured on the HOTPLUG event."""
    ec2 = session_cloud.cloud_instance.client
    with session_cloud.launch(launch_kwargs={}, user_data=USER_DATA) as client:
        ips_before = _get_ip_addr(client)
        instance_pub_ip = client.instance.ip
        secondary_priv_ip = client.instance.add_network_interface()
        response = ec2.describe_network_interfaces(
            Filters=[
                {
                    "Name": "private-ip-address",
                    "Values": [secondary_priv_ip],
                },
            ],
        )
        nic_id = response["NetworkInterfaces"][0]["NetworkInterfaceId"]

        # Create Elastic IP
        # Refactor after https://github.com/canonical/pycloudlib/issues/337 is
        # completed
        allocation = ec2.allocate_address(Domain="vpc")
        try:
            secondary_pub_ip = allocation["PublicIp"]
            association = ec2.associate_address(
                AllocationId=allocation["AllocationId"],
                NetworkInterfaceId=nic_id,
            )
            assert association["ResponseMetadata"]["HTTPStatusCode"] == 200

            _wait_till_hotplug_complete(client)

            log_content = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log_content)

            ips_after_add = _get_ip_addr(client)

            netplan_cfg = client.read_from_file(
                "/etc/netplan/50-cloud-init.yaml"
            )
            config = yaml.safe_load(netplan_cfg)
            new_addition = [
                ip for ip in ips_after_add if ip.ip4 == secondary_priv_ip
            ][0]
            assert new_addition.interface in config["network"]["ethernets"]
            new_nic_cfg = config["network"]["ethernets"][
                new_addition.interface
            ]
            assert "routing-policy" in new_nic_cfg
            assert [{"from": secondary_priv_ip, "table": 101}] == new_nic_cfg[
                "routing-policy"
            ]

            assert len(ips_after_add) == len(ips_before) + 1

            # SSH over primary NIC works
            subp("nc -w 5 -zv " + instance_pub_ip + " 22", shell=True)

            # THE TEST: SSH over secondary NIC works
            subp("nc -w 5 -zv " + secondary_pub_ip + " 22", shell=True)

            # Remove new NIC
            client.instance.remove_network_interface(secondary_priv_ip)
            _wait_till_hotplug_complete(client, expected_runs=2)

            # SSH over primary NIC works
            subp("nc -w 1 -zv " + instance_pub_ip + " 22", shell=True)

            ips_after_remove = _get_ip_addr(client)
            assert len(ips_after_remove) == len(ips_before)
            assert secondary_priv_ip not in [ip.ip4 for ip in ips_after_remove]

            netplan_cfg = client.read_from_file(
                "/etc/netplan/50-cloud-init.yaml"
            )
            config = yaml.safe_load(netplan_cfg)
            assert new_addition.interface not in config["network"]["ethernets"]

            log_content = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log_content)
        finally:
            with contextlib.suppress(Exception):
                ec2.disassociate_address(
                    AssociationId=association["AssociationId"]
                )
            with contextlib.suppress(Exception):
                ec2.release_address(AllocationId=allocation["AllocationId"])


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
@pytest.mark.user_data(USER_DATA)
def test_no_hotplug_triggered_by_docker(client: IntegrationInstance):
    # Install docker
    r = client.execute("curl -fsSL https://get.docker.com | sh")
    assert r.ok, r.stderr

    # Start and stop a container
    r = client.execute("docker run -dit --name ff ubuntu:focal")
    assert r.ok, r.stderr
    r = client.execute("docker stop ff")
    assert r.ok, r.stderr

    # Verify hotplug-hook was not called
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert "hotplug-hook" not in log

    # Verify hotplug was enabled
    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )
