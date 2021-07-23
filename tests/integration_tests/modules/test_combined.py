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
from tests.integration_tests.util import verify_ordered_items_in_text

USER_DATA = """\
#cloud-config
apt:
  primary:
    - arches: [default]
      uri: http://us.archive.ubuntu.com/ubuntu/
byobu_by_default: enable
final_message: |
  This is my final message!
  $version
  $timestamp
  $datasource
  $uptime
locale: en_GB.UTF-8
locale_configfile: /etc/default/locale
ntp:
  servers: ['ntp.ubuntu.com']
"""


@pytest.mark.user_data(USER_DATA)
class TestCombined:
    def test_final_message(self, class_client: IntegrationInstance):
        """Test that final_message module works as expected.

        Also tests LP 1511485: final_message is silent
        """
        client = class_client
        log = client.read_from_file('/var/log/cloud-init.log')
        today = date.today().strftime('%a, %d %b %Y')
        expected = (
            'This is my final message!\n'
            r'\d+\.\d+\n'
            '{}.*\n'
            'DataSource.*\n'
            r'\d+\.\d+'
        ).format(today)

        assert re.search(expected, log)

    def test_ntp_with_apt(self, class_client: IntegrationInstance):
        """LP #1628337.

        cloud-init tries to install NTP before even
        configuring the archives.
        """
        client = class_client
        log = client.read_from_file('/var/log/cloud-init.log')
        assert 'W: Failed to fetch' not in log
        assert 'W: Some index files failed to download' not in log
        assert 'E: Unable to locate package ntp' not in log

    def test_byobu(self, class_client: IntegrationInstance):
        """Test byobu configured as enabled by default."""
        client = class_client
        assert client.execute('test -e "/etc/byobu/autolaunch"').ok

    def test_configured_locale(self, class_client: IntegrationInstance):
        """Test locale can be configured correctly."""
        client = class_client
        default_locale = client.read_from_file('/etc/default/locale')
        assert 'LANG=en_GB.UTF-8' in default_locale

        locale_a = client.execute('locale -a')
        verify_ordered_items_in_text([
            'en_GB.utf8',
            'en_US.utf8'
        ], locale_a)

        locale_gen = client.execute(
            "cat /etc/locale.gen | grep -v '^#' | uniq"
        )
        verify_ordered_items_in_text([
            'en_GB.UTF-8',
            'en_US.UTF-8'
        ], locale_gen)
