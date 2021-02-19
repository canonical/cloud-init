"""Integration test for LP: #1901011

Ensure an ephemeral disk exists after boot.

See https://github.com/canonical/cloud-init/pull/800
"""
import re

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
            'Ephemeral resource disk .* exists. Merging default Azure cloud '
            'ephemeral disk configs.'
        )
    else:
        expected_log = (
            'Ephemeral resource disk .* does not exist. Not merging '
            'default Azure cloud ephemeral disk configs.'
        )

    with session_cloud.launch(
        launch_kwargs={'instance_type': instance_type}
    ) as client:
        log = client.read_from_file('/var/log/cloud-init.log')
        assert re.search(expected_log, log) is not None
