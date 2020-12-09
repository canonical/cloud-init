"""Integration test for lp-1813396

Ensure gpg works even if VM provides no /dev/tty"""

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.log_utils import ordered_items_in_text


USER_DATA = """\
#cloud-config
apt:
  sources:
    docker:
      source: 'deb [arch=amd64] https://download.docker.com/linux/debian stretch stable'
      keyserver: keyserver.ubuntu.com
      keyid: 0EBFCD88
"""  # noqa: E501


@pytest.mark.sru_2020_11
@pytest.mark.user_data(USER_DATA)
def test_gpg_no_tty(client: IntegrationInstance):
    log = client.read_from_file('/var/log/cloud-init.log')
    to_verify = [
        "Running command ['gpg', '--no-tty', "
        "'--keyserver=keyserver.ubuntu.com', '--recv-keys', '0EBFCD88'] "
        "with allowed return codes [0] (shell=False, capture=True)",
        "Imported key '0EBFCD88' from keyserver 'keyserver.ubuntu.com'",
        "finish: modules-config/config-apt-configure: SUCCESS",
    ]
    assert ordered_items_in_text(to_verify, log)
