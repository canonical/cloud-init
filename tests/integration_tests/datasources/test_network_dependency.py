import pytest

from tests.integration_tests.instances import IntegrationInstance


def _customize_envionment(client: IntegrationInstance):
    # Insert our "disable_network_activation" file here
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-disable-network-activation.cfg",
        "disable_network_activation: true\n",
    )
    client.execute("cloud-init clean --logs")
    client.restart()


# This test should be able to work on any cloud whose datasource specifies
# a NETWORK dependency
@pytest.mark.gce
@pytest.mark.ubuntu  # Because netplan
def test_network_activation_disabled(client: IntegrationInstance):
    """Test that the network is not activated during init mode."""
    _customize_envionment(client)
    result = client.execute("systemctl status google-guest-agent.service")
    if not result.ok:
        raise AssertionError(
            "google-guest-agent is not active:\n%s", result.stdout
        )
    log = client.read_from_file("/var/log/cloud-init.log")

    assert "Running command ['netplan', 'apply']" not in log

    assert "Not bringing up newly configured network interfaces" in log
    assert "Bringing up newly configured network interfaces" not in log
