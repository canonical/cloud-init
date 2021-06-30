# This file is part of cloud-init. See LICENSE file for license information.
"""A set of somewhat unrelated tests that can be combined into a single
instance launch. Generally tests should only be added here if a failure
of the test would be unlikely to affect the running of another test using
the same instance launch.
"""
import pytest
import re
from datetime import date

from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
final_message: |
  This is my final message!
  $version
  $timestamp
  $datasource
  $uptime
ntp:
  servers: ['ntp.ubuntu.com']
apt:
  primary:
    - arches: [default]
    uri: http://us.archive.ubuntu.com/ubuntu/
"""


@pytest.mark.userdata(USER_DATA)
def test_final_message(module_client: IntegrationInstance):
    """ Test that final_message module works as expected.

    Also tests LP 1511485: final_message is silent
    """
    client = module_client

    log = client.read_from_file('/var/log/cloud-init.log')
    today = date.today().strftime('%a, %d %b %Y')
    expected = (
        'This is my final message!\n'
        r'\d\d\.\d\n'
        '{}.*\n'
        'DataSource.*\n'
        r'\d+\.\d+'
    ).format(today)

    assert re.search(expected, log)


@pytest.mark.userdata(USER_DATA)
def test_ntp_with_apt(module_client: IntegrationInstance):
    """ LP #1628337.

    cloud-init tries to install NTP before even
    configuring the archives.
    """
    client = module_client

    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'W: Failed to fetch' not in log
    assert 'W: Some index files failed to download' not in log
    assert 'E: Unable to locate package ntp' not in log
