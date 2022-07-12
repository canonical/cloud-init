import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

UA_CLOUD_CONFIG = "/etc/cloud/cloud.cfg/05-pro.conf"

AUTO_ATTACH_DISABLED = """\
#cloud-config
ubuntu_advantage:
  disable_auto_attach: true
"""


def did_ua_service_noop(client: IntegrationInstance) -> bool:
    """Determine if ua.service did run or not"""
    raise NotImplementedError("TODO")


@pytest.mark.ubuntu
@pytest.mark.user_data(AUTO_ATTACH_DISABLED)
@pytest.mark.skip(reason="TODO")
def test_ubuntu_advantage_noop(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert did_ua_service_noop(client)


@pytest.mark.ubuntu
@pytest.mark.skip(reason="TODO")
def test_ubuntu_advantage_noop_cloud_cfg(client: IntegrationInstance):
    client.write_to_file(UA_CLOUD_CONFIG, AUTO_ATTACH_DISABLED)
    client.execute("cloud-init clean --logs --reboot")
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert did_ua_service_noop(client)


CUSTOM_SERVICES = """\
ubuntu_advantage:
  features:
    ignore_enable_by_default: true
    allow_beta: true
  enable:
  - fips
  enable_beta:
  - realtime-kernel
"""


@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.ubuntu
@pytest.mark.user_data(CUSTOM_SERVICES)
@pytest.mark.skip(reason="TODO")
def test_ubuntu_advantage_custom_services(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert did_ua_service_noop(client)
    # TODO check that cc_ubuntu_advantage did auto-attach properly
    # TODO check only fips and realtime-kernel are enabled


DISALLOW_BETA = """\
ubuntu_advantage:
  features:
    ignore_enable_by_default: true
    allow_beta: false
  enable:
  - realtime-kernel
"""


@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.ubuntu
@pytest.mark.user_data(DISALLOW_BETA)
@pytest.mark.skip(reason="TODO")
def test_ubuntu_advantage_disallow_beta(client: IntegrationInstance):
    assert did_ua_service_noop(client)
    # log = client.read_from_file("/var/log/cloud-init.log")
    # TODO check that cc_ubuntu_advantage did handle ua auto-attach errors
