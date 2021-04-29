"""Test user-overridable events.

This is currently limited to applying network config on BOOT events.
"""

import pytest
import re
import yaml

from tests.integration_tests.instances import IntegrationInstance


def _add_dummy_bridge_to_netplan(client: IntegrationInstance):
    # Update netplan configuration to ensure it doesn't change on reboot
    netplan = yaml.safe_load(
        client.execute('cat /etc/netplan/50-cloud-init.yaml')
    )
    # Just a dummy bridge to do nothing
    try:
        netplan['network']['bridges']['dummy0'] = {'dhcp4': False}
    except KeyError:
        netplan['network']['bridges'] = {'dummy0': {'dhcp4': False}}

    dumped_netplan = yaml.dump(netplan)
    client.write_to_file('/etc/netplan/50-cloud-init.yaml', dumped_netplan)


@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.oci
@pytest.mark.openstack
@pytest.mark.not_xenial
def test_boot_event_disabled_by_default(client: IntegrationInstance):
    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Applying network configuration' in log
    assert 'dummy0' not in client.execute('ls /sys/class/net')

    _add_dummy_bridge_to_netplan(client)
    client.execute('rm /var/log/cloud-init.log')

    client.restart()
    log2 = client.read_from_file('/var/log/cloud-init.log')

    # We attempt to apply network config twice on every boot.
    # Ensure neither time works.
    assert 2 == len(
        re.findall(r"Event Denied: scopes=\['network'\] EventType=boot[^-]",
                   log2)
    )
    assert 2 == log2.count(
        "Event Denied: scopes=['network'] EventType=boot-legacy"
    )
    assert 2 == log2.count(
        "No network config applied. Neither a new instance"
        " nor datasource network update allowed"
    )

    assert 'dummy0' in client.execute('ls /sys/class/net')


def _test_network_config_applied_on_reboot(client: IntegrationInstance):
    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Applying network configuration' in log
    assert 'dummy0' not in client.execute('ls /sys/class/net')

    _add_dummy_bridge_to_netplan(client)
    client.execute('rm /var/log/cloud-init.log')
    client.restart()
    log = client.read_from_file('/var/log/cloud-init.log')

    assert 'Event Allowed: scope=network EventType=boot' in log
    assert 'Applying network configuration' in log
    assert 'dummy0' not in client.execute('ls /sys/class/net')


@pytest.mark.azure
@pytest.mark.not_xenial
def test_boot_event_enabled_by_default(client: IntegrationInstance):
    _test_network_config_applied_on_reboot(client)


USER_DATA = """\
#cloud-config
updates:
  network:
    when: [boot]
"""


@pytest.mark.not_xenial
@pytest.mark.user_data(USER_DATA)
def test_boot_event_enabled(client: IntegrationInstance):
    _test_network_config_applied_on_reboot(client)
