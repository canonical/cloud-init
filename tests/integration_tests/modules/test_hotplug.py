import time
from collections import namedtuple

import pytest
import yaml

from cloudinit.subp import subp
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import (
    CURRENT_RELEASE,
    FOCAL,
    UBUNTU_STABLE,
)
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
updates:
  network:
    when: ['hotplug']
"""

USER_DATA_HOTPLUG_DISABLED = """\
#cloud-config
updates:
  network:
    when: ['boot-new-instance']
"""

ip_addr = namedtuple("ip_addr", "interface state ip4 ip6")


def _wait_till_hotplug_complete(client, expected_runs=1):
    for _ in range(60):
        if client.execute("command -v systemctl").ok:
            if "failed" == client.execute(
                "systemctl is-active cloud-init-hotplugd.service"
            ):
                r = client.execute(
                    "systemctl status cloud-init-hotplugd.service"
                )
                if not r.ok:
                    raise AssertionError(
                        "cloud-init-hotplugd.service failed: {r.stdout}"
                    )

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
        # The output of `ip --brief addr` can contain metric info:
        # ens5 UP <ipv4_cidr> metric 100 <ipv6_cidr> ...
        ip6_cidr = None
        if len(attributes) > 3:
            if attributes[3] != "metric":
                ip6_cidr = attributes[3]
            elif len(attributes) > 5:
                ip6_cidr = attributes[5]
        ip4 = ip4_cidr.split("/")[0] if ip4_cidr else None
        ip6 = ip6_cidr.split("/")[0] if ip6_cidr else None
        ip = ip_addr(interface, state, ip4, ip6)
        ips.append(ip)
    return ips


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        "Test was written for openstack but can likely run on other platforms."
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
    PLATFORM not in ["lxd_container", "lxd_vm", "ec2", "openstack", "azure"],
    reason=(f"HOTPLUG is not supported in {PLATFORM}."),
)
def _test_hotplug_enabled_by_cmd(client: IntegrationInstance):
    assert "disabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )
    ret = client.execute("cloud-init devel hotplug-hook -s net enable")
    assert ret.ok, ret.stderr
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "hotplug-hook called with the following arguments: "
        "{hotplug_action: enable" in log
    )

    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "hotplug-hook called with the following arguments: "
        "{hotplug_action: query" in log
    )
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).ok


@pytest.mark.user_data(USER_DATA_HOTPLUG_DISABLED)
def test_hotplug_enable_cmd(client: IntegrationInstance):
    _test_hotplug_enabled_by_cmd(client)


@pytest.mark.skipif(
    PLATFORM != "ec2",
    reason=(
        f"Test was written for {PLATFORM} but can likely run on "
        "other platforms."
    ),
)
@pytest.mark.user_data(USER_DATA_HOTPLUG_DISABLED)
def test_hotplug_enable_cmd_ec2(client: IntegrationInstance):
    _test_hotplug_enabled_by_cmd(client)
    ips_before = _get_ip_addr(client)

    # Add new NIC
    added_ip = client.instance.add_network_interface()
    _wait_till_hotplug_complete(client, expected_runs=4)
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
    _wait_till_hotplug_complete(client, expected_runs=5)
    ips_after_remove = _get_ip_addr(client)
    assert len(ips_after_remove) == len(ips_before)
    assert added_ip not in [ip.ip4 for ip in ips_after_remove]

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface not in config["network"]["ethernets"]


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        "Test was written for openstack but can likely run on other platforms."
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
    with session_cloud.launch(launch_kwargs={}, user_data=USER_DATA) as client:
        ips_before = _get_ip_addr(client)
        secondary_priv_ip = client.instance.add_network_interface(
            ipv4_public_ip_count=1,
        )
        _wait_till_hotplug_complete(client, expected_runs=1)

        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)

        ips_after_add = _get_ip_addr(client)

        netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        config = yaml.safe_load(netplan_cfg)
        new_addition = [
            ip for ip in ips_after_add if ip.ip4 == secondary_priv_ip
        ][0]
        assert new_addition.interface in config["network"]["ethernets"]
        new_nic_cfg = config["network"]["ethernets"][new_addition.interface]
        assert [{"from": secondary_priv_ip, "table": 101}] == new_nic_cfg[
            "routing-policy"
        ]

        assert len(ips_after_add) == len(ips_before) + 1
        public_ips = client.instance.public_ips
        assert len(public_ips) == 2

        # SSH over all public ips works
        for pub_ip in public_ips:
            subp("nc -w 5 -zv " + pub_ip + " 22", shell=True)

        # Remove new NIC
        client.instance.remove_network_interface(secondary_priv_ip)
        _wait_till_hotplug_complete(client, expected_runs=2)

        public_ips = client.instance.public_ips
        assert len(public_ips) == 1
        # SSH over primary NIC works
        subp("nc -w 1 -zv " + public_ips[0] + " 22", shell=True)

        ips_after_remove = _get_ip_addr(client)
        assert len(ips_after_remove) == len(ips_before)
        assert secondary_priv_ip not in [ip.ip4 for ip in ips_after_remove]

        netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        config = yaml.safe_load(netplan_cfg)
        assert new_addition.interface not in config["network"]["ethernets"]

        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)


@pytest.mark.skipif(CURRENT_RELEASE <= FOCAL, reason="See LP: #2055397")
@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_multi_nic_hotplug_vpc(setup_image, session_cloud: IntegrationCloud):
    """Tests that additional secondary NICs are routable from local
    networks after the hotplug hook is executed when network updates
    are configured on the HOTPLUG event."""
    with session_cloud.launch(
        user_data=USER_DATA
    ) as client, session_cloud.launch() as bastion:
        ips_before = _get_ip_addr(client)
        primary_priv_ip4 = ips_before[1].ip4
        primary_priv_ip6 = ips_before[1].ip6
        client.instance.add_network_interface(ipv6_address_count=1)

        _wait_till_hotplug_complete(client)
        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)

        netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        config = yaml.safe_load(netplan_cfg)

        ips_after_add = _get_ip_addr(client)
        secondary_priv_ip4 = ips_after_add[2].ip4
        secondary_priv_ip6 = ips_after_add[2].ip6
        assert primary_priv_ip4 != secondary_priv_ip4

        new_addition = [
            ip for ip in ips_after_add if ip.ip4 == secondary_priv_ip4
        ][0]
        assert new_addition.interface in config["network"]["ethernets"]
        new_nic_cfg = config["network"]["ethernets"][new_addition.interface]
        assert "routing-policy" in new_nic_cfg
        assert [
            {"from": secondary_priv_ip4, "table": 101},
            {"from": secondary_priv_ip6, "table": 101},
        ] == new_nic_cfg["routing-policy"]

        assert len(ips_after_add) == len(ips_before) + 1

        # pings to primary and secondary NICs work
        r = bastion.execute(f"ping -c1 {primary_priv_ip4}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 {secondary_priv_ip4}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 {primary_priv_ip6}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 {secondary_priv_ip6}")
        assert r.ok, r.stdout

        # Remove new NIC
        client.instance.remove_network_interface(secondary_priv_ip4)
        _wait_till_hotplug_complete(client, expected_runs=2)

        # ping to primary NIC works
        assert bastion.execute(f"ping -c1 {primary_priv_ip4}").ok
        assert bastion.execute(f"ping -c1 {primary_priv_ip6}").ok

        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
@pytest.mark.skipif(
    CURRENT_RELEASE not in UBUNTU_STABLE,
    reason="Docker repo does not contain pkgs for non stable releases.",
)
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
