# This file is part of cloud-init. See LICENSE file for license information.
import os
import pytest
from contextlib import contextmanager

from tests.integration_tests import integration_settings
from tests.integration_tests.platforms import (
    dynamic_client,
    LxdContainerClient,
    client_name_to_class
)


def pytest_runtest_setup(item):
    """Skip tests on unsupported clouds.

    A test can take any number of marks to specify the platforms it can
    run on. If a platform(s) is specified and we're not running on that
    platform, then skip the test. If platform specific marks are not
    specified, then we assume the test can be run anywhere.
    """
    all_platforms = client_name_to_class.keys()
    supported_platforms = set(all_platforms).intersection(
        mark.name for mark in item.iter_markers())
    current_platform = integration_settings.PLATFORM
    if supported_platforms and current_platform not in supported_platforms:
        pytest.skip('Cannot run on platform {}'.format(current_platform))


# disable_subp_usage is defined at a higher level, but we don't
# want it applied here
@pytest.fixture()
def disable_subp_usage(request):
    pass


@pytest.fixture(scope='session', autouse=True)
def common_environment():
    """Setup the target environment with the correct version of cloud-init.

    So we can launch instances / run tests with the correct image
    """
    client = dynamic_client()
    print('Setting up environment for {}'.format(client.datasource))
    if integration_settings.IMAGE_SOURCE == 'NONE':
        pass  # that was easy
    elif integration_settings.IMAGE_SOURCE == 'IN_PLACE':
        if not isinstance(client, LxdContainerClient):
            raise ValueError('IN_PLACE as IMAGE_SOURCE only works for LXD')
        # The mount needs to happen after the instance is launched, so
        # no further action needed here
    elif integration_settings.IMAGE_SOURCE == 'PROPOSED':
        client.launch()
        client.install_proposed_image()
    elif integration_settings.IMAGE_SOURCE.startswith('ppa:'):
        client.launch()
        client.install_ppa(integration_settings.IMAGE_SOURCE)
    elif os.path.isfile(str(integration_settings.IMAGE_SOURCE)):
        client.launch()
        client.install_deb()
    if client.instance:
        # Even if we're keeping instances, we don't want to keep this
        # one around as it was just for image creation
        client.destroy()
    print('Done with environment setup')


@contextmanager
def _client(request, fixture_utils):
    cloud_config = fixture_utils.closest_marker_first_arg_or(
        request, 'cloud_config', None)
    with dynamic_client(user_data=cloud_config) as instance:
        yield instance


@pytest.yield_fixture
def client(request, fixture_utils):
    with _client(request, fixture_utils) as client:
        yield client


@pytest.yield_fixture(scope='module')
def module_client(request, fixture_utils):
    with _client(request, fixture_utils) as client:
        yield client


@pytest.yield_fixture(scope='class')
def class_client(request, fixture_utils):
    with _client(request, fixture_utils) as client:
        yield client
