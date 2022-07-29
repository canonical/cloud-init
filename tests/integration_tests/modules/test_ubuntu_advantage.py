import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

UA_CLOUD_CONFIG = "/etc/cloud/cloud.cfg/05-pro.conf"

AUTO_ATTACH_DISABLED = """\
#cloud-config
apt:
  ppa:ua-client/daily
ubuntu_advantage:
  disable_auto_attach: true
"""

CUSTOM_SERVICES = """\
ubuntu_advantage:
enable:
- fips
enable_beta:
- realtime-kernel
"""


DISABLED_SERVICES = """\
ubuntu_advantage:
enable: []
enable_beta: []
"""


def did_ua_service_noop(client: IntegrationInstance) -> bool:
    """Determine if ua.service did run or not"""
    raise NotImplementedError("TODO")


@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.ubuntu
@pytest.mark.ci
class TestUbuntuAdvantagePro:
    @pytest.mark.user_data(AUTO_ATTACH_DISABLED)
    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_noop(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)

    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_noop_cloud_cfg(
        self, client: IntegrationInstance
    ):
        client.write_to_file(UA_CLOUD_CONFIG, AUTO_ATTACH_DISABLED)
        client.execute("cloud-init clean --logs --reboot")
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)

    @pytest.mark.user_data(CUSTOM_SERVICES)
    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_custom_services(
        self, client: IntegrationInstance
    ):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)
        # TODO check that cc_ubuntu_advantage did auto-attach properly
        # TODO check only fips and realtime-kernel are enabled

    @pytest.mark.user_data(DISABLED_SERVICES)
    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_disabled_services(
        self, client: IntegrationInstance
    ):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)
        # TODO check that cc_ubuntu_advantage did auto-attach properly
        # TODO check all services are disabled
