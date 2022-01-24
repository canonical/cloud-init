"""Test loading the network config"""
import pytest

from tests.integration_tests.instances import IntegrationInstance


def _customize_envionment(client: IntegrationInstance):
    # Insert our "disable_network_config" file here
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg",
        "network: {config: disabled}\n",
    )
    client.execute("cloud-init clean --logs")
    client.restart()


def test_network_disabled_via_etc_cloud(client: IntegrationInstance):
    """Test that network can be disabled via config file in /etc/cloud"""
    if client.settings.CLOUD_INIT_SOURCE == "IN_PLACE":
        pytest.skip(
            "IN_PLACE not supported as we mount /etc/cloud contents into the "
            "container"
        )
    _customize_envionment(client)

    log = client.read_from_file("/var/log/cloud-init.log")
    assert "network config is disabled by system_cfg" in log
