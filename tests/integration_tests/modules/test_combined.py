# This file is part of cloud-init. See LICENSE file for license information.
"""A set of somewhat unrelated tests that can be combined into a single
instance launch. Generally tests should only be added here if a failure
of the test would be unlikely to affect the running of another test using
the same instance launch. Most independent module coherence tests can go
here.
"""
import json
import pytest
import re
from datetime import date

from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_ordered_items_in_text

USER_DATA = """\
## template: jinja
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
runcmd:
  - echo {{ds.meta_data.local_hostname}} > /var/tmp/runcmd_output
  - echo {{merged_cfg.def_log_file}} >> /var/tmp/runcmd_output
"""


@pytest.mark.ci
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
            r'\d+\.\d+.*\n'
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

    def test_runcmd_with_variable_substitution(
        self, class_client: IntegrationInstance
    ):
        """Test runcmd, while including jinja substitution.

        Ensure we can also substitue variables from instance-data-sensitive
        LP: #1931392
        """
        client = class_client
        expected = [
            client.execute('hostname').stdout.strip(),
            '/var/log/cloud-init.log',
        ]
        output = client.read_from_file('/var/tmp/runcmd_output')
        verify_ordered_items_in_text(expected, output)

    def test_no_problems(self, class_client: IntegrationInstance):
        """Test no errors, warnings, or tracebacks"""
        client = class_client
        status_file = client.read_from_file('/run/cloud-init/status.json')
        status_json = json.loads(status_file)['v1']
        for stage in ('init', 'init-local', 'modules-config', 'modules-final'):
            assert status_json[stage]['errors'] == []
        result_file = client.read_from_file('/run/cloud-init/result.json')
        result_json = json.loads(result_file)['v1']
        assert result_json['errors'] == []

        log = client.read_from_file('/var/log/cloud-init.log')
        assert 'WARN' not in log
        assert 'Traceback' not in log

    def _check_common_metadata(self, data):
        assert data['base64_encoded_keys'] == []
        assert data['merged_cfg'] == 'redacted for non-root user'

        image_spec = ImageSpecification.from_os_image()
        assert data['sys_info']['dist'][0] == image_spec.os

        v1_data = data['v1']
        assert re.match(r'\d\.\d+\.\d+-\d+', v1_data['kernel_release'])
        assert v1_data['variant'] == image_spec.os
        assert v1_data['distro'] == image_spec.os
        assert v1_data['distro_release'] == image_spec.release
        assert v1_data['machine'] == 'x86_64'
        assert re.match(r'3.\d\.\d', v1_data['python_version'])

    @pytest.mark.lxd_container
    def test_instance_json_lxd(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            '/run/cloud-init/instance-data.json')

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data['v1']
        assert v1_data['cloud_name'] == 'unknown'
        assert v1_data['platform'] == 'lxd'
        assert v1_data['subplatform'] == (
            'seed-dir (/var/lib/cloud/seed/nocloud-net)')
        assert v1_data['availability_zone'] is None
        assert v1_data['instance_id'] == client.instance.name
        assert v1_data['local_hostname'] == client.instance.name
        assert v1_data['region'] is None

    @pytest.mark.lxd_vm
    def test_instance_json_lxd_vm(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            '/run/cloud-init/instance-data.json')

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data['v1']
        assert v1_data['cloud_name'] == 'unknown'
        assert v1_data['platform'] == 'lxd'
        assert v1_data['subplatform'] == (
            'seed-dir (/var/lib/cloud/seed/nocloud-net)')
        assert v1_data['availability_zone'] is None
        assert v1_data['instance_id'] == client.instance.name
        assert v1_data['local_hostname'] == client.instance.name
        assert v1_data['region'] is None

    @pytest.mark.ec2
    def test_instance_json_ec2(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            '/run/cloud-init/instance-data.json')
        data = json.loads(instance_json_file)
        v1_data = data['v1']
        assert v1_data['cloud_name'] == 'aws'
        assert v1_data['platform'] == 'ec2'
        assert v1_data['subplatform'].startswith('metadata')
        assert v1_data[
            'availability_zone'] == client.instance.availability_zone
        assert v1_data['instance_id'] == client.instance.name
        assert v1_data['local_hostname'].startswith('ip-')
        assert v1_data['region'] == client.cloud.cloud_instance.region
