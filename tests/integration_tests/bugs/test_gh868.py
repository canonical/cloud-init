"""Ensure no Traceback when 'chef_license' is set"""
import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

USERDATA = """\
#cloud-config
chef:
  install_type: omnibus
  chef_license: accept
  server_url: https://chef.yourorg.invalid
  validation_name: some-validator
"""


@pytest.mark.adhoc  # Can't be regularly reaching out to chef install script
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.azure
@pytest.mark.oci
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.user_data(USERDATA)
def test_chef_license(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
