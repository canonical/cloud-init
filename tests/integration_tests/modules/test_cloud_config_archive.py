import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_boot, verify_clean_log

USER_DATA = """\
#cloud-config-archive
- type: "text/cloud-boothook"
  content: |
    #!/bin/sh
    echo "this is from a boothook." > /var/tmp/boothook.txt
- type: "text/cloud-config"
  content: |
    bootcmd:
    - echo "this is from a cloud-config." > /var/tmp/bootcmd.txt
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
def test_cloud_config_archive(client: IntegrationInstance):
    """Basic correctness test for #cloud-config-archive."""
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "this is from a boothook." in client.read_from_file(
        "/var/tmp/boothook.txt"
    )
    assert "this is from a cloud-config." in client.read_from_file(
        "/var/tmp/bootcmd.txt"
    )
    verify_clean_log(log)
    verify_clean_boot(client)
