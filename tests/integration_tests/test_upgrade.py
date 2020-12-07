import logging
import pytest
from pathlib import Path

from tests.integration_tests.clouds import ImageSpecification, IntegrationCloud
from tests.integration_tests.conftest import (
    get_validated_source,
    session_start_time,
)

log = logging.getLogger('integration_testing')

USER_DATA = """\
#cloud-config
hostname: SRU-worked
"""


def _output_to_compare(instance, file_path, netcfg_path):
    commands = [
        'hostname',
        'dpkg-query --show cloud-init',
        'cat /run/cloud-init/result.json',
        'grep Trace /var/log/cloud-init.log',
        'cloud-id'
        'cat {}'.format(netcfg_path),
        'systemd-analyze',
        'systemd-analyze blame',
        'cloud-init analyze show',
        'cloud-init analyze blame',
    ]
    with file_path.open('w') as f:
        for command in commands:
            f.write('===== {} ====='.format(command) + '\n')
            f.write(instance.execute(command) + '\n')


@pytest.mark.sru_2020_11
def test_upgrade(session_cloud: IntegrationCloud):
    source = get_validated_source()
    if not source.installs_new_version():
        pytest.skip("Install method '{}' not supported for this test".format(
            source
        ))
        return  # type checking doesn't understand that skip raises

    launch_kwargs = {
        'name': 'integration-upgrade-test',
        'image_id': session_cloud._get_initial_image(),
        'wait': True,
    }

    image = ImageSpecification.from_os_image()

    # Get the paths to write test logs
    output_dir = Path(session_cloud.settings.LOCAL_LOG_PATH)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_filename = 'test_upgrade_{os}_{{stage}}_{time}.log'.format(
        os=image.release,
        time=session_start_time,
    )
    before_path = output_dir / base_filename.format(stage='before')
    after_path = output_dir / base_filename.format(stage='after')

    # Get the network cfg file
    netcfg_path = '/dev/null'
    if image.os == 'ubuntu':
        netcfg_path = '/etc/netplan/50-cloud-init.yaml'
        if image.release == 'xenial':
            netcfg_path = '/etc/network/interfaces.d/50-cloud-init.cfg'

    with session_cloud.launch(
        launch_kwargs=launch_kwargs, user_data=USER_DATA
    ) as instance:
        _output_to_compare(instance, before_path, netcfg_path)
        instance.install_new_cloud_init(source, take_snapshot=False)
        instance.execute('hostname something-else')
        instance.restart(raise_on_cloudinit_failure=True)
        _output_to_compare(instance, after_path, netcfg_path)

    log.info('Wrote upgrade test logs to %s and %s', before_path, after_path)
