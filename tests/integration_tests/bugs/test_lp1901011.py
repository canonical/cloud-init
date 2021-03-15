"""Integration test for LP: #1901011

Ensure an ephemeral disk exists after boot.

See https://github.com/canonical/cloud-init/pull/800
"""
import pytest

from tests.integration_tests.clouds import IntegrationCloud


@pytest.mark.azure
@pytest.mark.parametrize('instance_type,is_ephemeral', [
    ('Standard_DS1_v2', True),
    ('Standard_D2s_v4', False),
])
def test_ephemeral(instance_type, is_ephemeral,
                   session_cloud: IntegrationCloud, setup_image):
    if is_ephemeral:
        expected_log = (
            "Ephemeral resource disk '/dev/disk/cloud/azure_resource' exists. "
            "Merging default Azure cloud ephemeral disk configs."
        )
    else:
        expected_log = (
            "Ephemeral resource disk '/dev/disk/cloud/azure_resource' does "
            "not exist. Not merging default Azure cloud ephemeral disk "
            "configs."
        )

    with session_cloud.launch(
        launch_kwargs={'instance_type': instance_type}
    ) as client:
        # Verify log file
        log = client.read_from_file('/var/log/cloud-init.log')
        assert expected_log in log

        # Verify devices
        dev_links = client.execute('ls /dev/disk/cloud')
        assert 'azure_root' in dev_links
        assert 'azure_root-part1' in dev_links
        if is_ephemeral:
            assert 'azure_resource' in dev_links
            assert 'azure_resource-part1' in dev_links

        # Verify mounts
        blks = client.execute('lsblk -pPo NAME,TYPE,MOUNTPOINT')
        root_device = client.execute(
            'realpath /dev/disk/cloud/azure_root-part1'
        )
        assert 'NAME="{}" TYPE="part" MOUNTPOINT="/"'.format(
            root_device) in blks
        if is_ephemeral:
            ephemeral_device = client.execute(
                'realpath /dev/disk/cloud/azure_resource-part1'
            )
            assert 'NAME="{}" TYPE="part" MOUNTPOINT="/mnt"'.format(
                ephemeral_device) in blks
