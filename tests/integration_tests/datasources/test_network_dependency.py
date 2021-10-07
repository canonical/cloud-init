import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source


def _setup_custom_image(session_cloud: IntegrationCloud):
    """Like `setup_image` in conftest.py, but with customized content."""
    source = get_validated_source(session_cloud)
    if not source.installs_new_version():
        return
    client = session_cloud.launch()

    # Insert our "disable_network_activation" file here
    client.write_to_file(
        '/etc/cloud/cloud.cfg.d/99-disable-network-activation.cfg',
        'disable_network_activation: true\n',
    )

    client.install_new_cloud_init(source)
    # Even if we're keeping instances, we don't want to keep this
    # one around as it was just for image creation
    client.destroy()


# This test should be able to work on any cloud whose datasource specifies
# a NETWORK dependency
@pytest.mark.gce
@pytest.mark.ubuntu  # Because netplan
def test_network_activation_disabled(session_cloud: IntegrationCloud):
    """Test that the network is not activated during init mode."""
    _setup_custom_image(session_cloud)
    with session_cloud.launch() as client:
        result = client.execute('systemctl status google-guest-agent.service')
        if not result.ok:
            raise AssertionError('google-guest-agent is not active:\n%s',
                                 result.stdout)
        log = client.read_from_file('/var/log/cloud-init.log')

    assert "Running command ['netplan', 'apply']" not in log

    assert 'Not bringing up newly configured network interfaces' in log
    assert 'Bringing up newly configured network interfaces' not in log
