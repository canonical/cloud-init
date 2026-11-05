"""Ensure no Traceback when 'chef_license' is set"""

import os
from urllib.parse import urlencode

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_boot, verify_clean_log

CHEF_LICENSE_KEY = os.environ.get("CLOUD_INIT_CHEF_LICENSE_KEY", "")
CHEF_INSTALL_URL = (
    "https://chefdownload-commercial.chef.io/install.sh?"
    + urlencode({"license_id": CHEF_LICENSE_KEY})
)

USERDATA = f"""\
#cloud-config
chef:
  install_type: omnibus
  omnibus_url: {CHEF_INSTALL_URL}
  chef_license: accept
  server_url: https://chef.yourorg.invalid
  validation_name: some-validator
"""


@pytest.mark.adhoc  # Can't be regularly reaching out to chef install script
@pytest.mark.skipif(
    "openstack" == PLATFORM, reason="Firewall preventing openstack run"
)
@pytest.mark.skipif(
    not CHEF_LICENSE_KEY,
    reason="CLOUD_INIT_CHEF_LICENSE_KEY environment variable not provided",
)
@pytest.mark.user_data(USERDATA)
def test_chef_license(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    verify_clean_boot(client)
