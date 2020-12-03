from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
import pytest


def _output_to_compare(instance):
    commands = [
        'hostname',
        'dpkg-query --show cloud-init',
        'cat /run/cloud-init/result.json',
        '! grep Trace /var/log/cloud-init.log',
        'systemd-analyze',
        'systemd-analyze blame',
        'cloud-init analyze show',
        'cloud-init analyze blame',
        'cat $NETCFG_FILE',
        'cloud-id'
    ]
    for command in commands:
        print('executing: {}'.format(command))
        print(instance.execute(command))


def test_upgrade(session_cloud: IntegrationCloud):
    try:
        install_method = get_validated_source()
    except ValueError:
        pytest.skip("Current install method not supported for this test")
        return  # type checking doesn't understand that skip raises

    launch_kwargs = {
        'name': 'integration-upgrade-test',
        'image_id': session_cloud._get_initial_image(),
        'wait': True,
    }
    with session_cloud.launch(launch_kwargs=launch_kwargs) as instance:
        print('Before upgrade')
        _output_to_compare(instance)
        instance.install_new_cloud_init(
            install_method, take_snapshot=False)
        instance.instance.restart()
        print('After upgrade')
        _output_to_compare(instance)
