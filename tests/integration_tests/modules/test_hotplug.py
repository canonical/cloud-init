import time
from collections import namedtuple

import pytest
import yaml

from tests.integration_tests.instances import IntegrationInstance

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


@pytest.mark.openstack
# On Bionic, we traceback when attempting to detect the hotplugged
# device in the updated metadata. This is because Bionic is specifically
# configured not to provide network metadata.
@pytest.mark.not_bionic
@pytest.mark.user_data(USER_DATA)
def test_hotplug_add_remove(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/10-cloud-init-hook-hotplug.rules"
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


@pytest.mark.openstack
def test_no_hotplug_in_userdata(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/10-cloud-init-hook-hotplug.rules"
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
