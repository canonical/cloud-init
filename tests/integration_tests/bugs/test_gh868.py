"""Ensure no Traceback when 'chef_license' is set"""

import os
from urllib.parse import urlencode

import pytest

from cloudinit.config.cc_chef import OMNIBUS_URL
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_boot, verify_clean_log

USERDATA = """\
#cloud-config
chef:
  install_type: omnibus
  omnibus_url: {chef_install_url}
  chef_license: accept
  server_url: https://chef.yourorg.invalid
  validation_name: some-validator
"""


def _get_chef_install_url() -> str:
    """Return the licensed Chef installer URL, or an empty string if unset."""
    chef_license_key = os.environ.get("CLOUD_INIT_CHEF_LICENSE_KEY", "")
    if not chef_license_key:
        return ""
    return f"{OMNIBUS_URL}?" + urlencode({"license_id": chef_license_key})


@pytest.mark.adhoc  # Can't be regularly reaching out to chef install script
@pytest.mark.skipif(
    "openstack" == PLATFORM, reason="Firewall preventing openstack run"
)
@pytest.mark.skipif(
    not _get_chef_install_url(),
    reason="CLOUD_INIT_CHEF_LICENSE_KEY environment var not provided",
)
@pytest.mark.user_data(
    USERDATA.format(chef_install_url=_get_chef_install_url())
)
def test_chef_license(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    verify_clean_boot(client)
