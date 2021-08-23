"""Ensure no Traceback when 'chef_license' is set"""
import pytest
from tests.integration_tests.instances import IntegrationInstance


USERDATA = """\
#cloud-config
chef:
  install_type: omnibus
  chef_license: accept
  server_url: https://chef.yourorg.invalid
  validation_name: some-validator
"""


@pytest.mark.adhoc  # Can't be regularly reaching out to chef install script
@pytest.mark.user_data(USERDATA)
def test_chef_license(client: IntegrationInstance):
    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Traceback' not in log
