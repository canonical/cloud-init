# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import pytest
import sys
from contextlib import contextmanager

from tests.integration_tests import integration_settings
from tests.integration_tests.instances import LxdContainerInstance
from tests.integration_tests.platform import (
    dynamic_instance,
    session_cloud,
    initialize_session_client,
    platforms
)


log = logging.getLogger('integration_testing')
log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.INFO)


def pytest_runtest_setup(item):
    """Skip tests on unsupported clouds.

    A test can take any number of marks to specify the platforms it can
    run on. If a platform(s) is specified and we're not running on that
    platform, then skip the test. If platform specific marks are not
    specified, then we assume the test can be run anywhere.
    """
    all_platforms = platforms.keys()
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


@pytest.yield_fixture(scope='session', autouse=True)
def setup_and_destroy_session():
    initialize_session_client()
    yield
    session_cloud().destroy()


@pytest.fixture(scope='session', autouse=True)
def setup_image(setup_and_destroy_session):
    """Setup the target environment with the correct version of cloud-init.

    So we can launch instances / run tests with the correct image
    """
    client = dynamic_instance()
    log.info('Setting up environment for %s', client.datasource)
    client.emit_settings_to_log()
    if integration_settings.CLOUD_INIT_SOURCE == 'NONE':
        pass  # that was easy
    elif integration_settings.CLOUD_INIT_SOURCE == 'IN_PLACE':
        if not isinstance(client, LxdContainerInstance):
            raise ValueError(
                'IN_PLACE as CLOUD_INIT_SOURCE only works for LXD')
        # The mount needs to happen after the instance is launched, so
        # no further action needed here
    elif integration_settings.CLOUD_INIT_SOURCE == 'PROPOSED':
        client.launch()
        client.install_proposed_image()
    elif integration_settings.CLOUD_INIT_SOURCE.startswith('ppa:'):
        client.launch()
        client.install_ppa(integration_settings.CLOUD_INIT_SOURCE)
    elif os.path.isfile(str(integration_settings.CLOUD_INIT_SOURCE)):
        client.launch()
        client.install_deb()
    else:
        raise ValueError(
            'Invalid value for CLOUD_INIT_SOURCE setting: {}'.format(
                integration_settings.CLOUD_INIT_SOURCE))
    if client.instance:
        # Even if we're keeping instances, we don't want to keep this
        # one around as it was just for image creation
        client.destroy()
    log.info('Done with environment setup')


@contextmanager
def _client(request, fixture_utils):
    """Fixture implementation for the client fixtures.

    Launch the dynamic IntegrationClient instance using any provided
    userdata, yield to the test, then cleanup
    """
    user_data = fixture_utils.closest_marker_first_arg_or(
        request, 'user_data', None)
    with dynamic_instance(user_data=user_data) as instance:
        yield instance


@pytest.yield_fixture
def client(request, fixture_utils):
    """Provide a client that runs for every test."""
    with _client(request, fixture_utils) as client:
        yield client


@pytest.yield_fixture(scope='module')
def module_client(request, fixture_utils):
    """Provide a client that runs once per module."""
    with _client(request, fixture_utils) as client:
        yield client


@pytest.yield_fixture(scope='class')
def class_client(request, fixture_utils):
    """Provide a client that runs once per class."""
    with _client(request, fixture_utils) as client:
        yield client


def pytest_assertrepr_compare(op, left, right):
    """Custom integration test assertion explanations.

    See
    https://docs.pytest.org/en/stable/assert.html#defining-your-own-explanation-for-failed-assertions
    for pytest's documentation.
    """
    if op == "not in" and isinstance(left, str) and isinstance(right, str):
        # This stanza emits an improved assertion message if we're testing for
        # the presence of a string within a cloud-init log: it will report only
        # the specific lines containing the string (instead of the full log,
        # the default behaviour).
        potential_log_lines = right.splitlines()
        first_line = potential_log_lines[0]
        if "DEBUG" in first_line and "Cloud-init" in first_line:
            # We are looking at a cloud-init log, so just pick out the relevant
            # lines
            found_lines = [
                line for line in potential_log_lines if left in line
            ]
            return [
                '"{}" not in cloud-init.log string; unexpectedly found on'
                " these lines:".format(left)
            ] + found_lines
