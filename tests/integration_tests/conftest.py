import os
import pytest

from tests.integration_tests import integration_settings
from tests.integration_tests.platforms import (
    dynamic_client,
    LxdContainerClient,
    ALL_PLATFORMS,
)


def pytest_runtest_setup(item):
    """
    A test can take any number of marks to specify the platforms it can
    run on. If a platform(s) is specified and we're not running on that
    platform, then skip the test. If platform specific marks are not
    specified, then we assume the test can be run anywhere
    """
    supported_platforms = set(ALL_PLATFORMS).intersection(
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
    """
    Setup the target environment with the correct version of cloud-init
    so we can launch instances / run tests with the correct image
    """
    client = dynamic_client()
    print('Setting up environment for {}'.format(client.datasource))
    if integration_settings.IMAGE_SOURCE == 'NONE':
        pass  # that was easy
    elif integration_settings.IMAGE_SOURCE == 'IN_PLACE':
        # pylxd version of
        # "lxc config device add my-cloud-test host-cloud-init disk
        # source=<path_to_repo>/cloudinit
        # path=/usr/lib/python3/dist-packages/cloudinit"
        if not isinstance(client, LxdContainerClient):
            raise ValueError('IN_PLACE as IMAGE_SOURCE only works for LXD')
        raise NotImplementedError  # Still not done
    elif integration_settings.IMAGE_SOURCE == 'CURRENT':
        raise NotImplementedError
    elif integration_settings.IMAGE_SOURCE == 'COMMIT':
        raise NotImplementedError
    elif integration_settings.IMAGE_SOURCE == 'PROPOSED':
        client.launch()
        client.generate_proposed_image()
    elif integration_settings.IMAGE_SOURCE == 'PPA':
        raise NotImplementedError
    elif os.path.isfile(str(integration_settings.IMAGE_SOURCE)):
        # Push deb to remote and install it...see existing impl
        raise NotImplementedError  # Not done yet
    if client.instance:
        # Even if we're keeping instances, we don't want to keep this
        # one around as it was just for image creation
        client.destroy()
    print('Done with environment setup')
