import os

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

UA_CLOUD_CONFIG = "/etc/cloud/cloud.cfg/05-pro.conf"

UA_TOKEN_VALID = os.environ.get("UA_TOKEN_VALID")

ATTACH_FALLBACK = """\
#cloud-config
ubuntu_advantage:
  features:
    disable_auto_attach: true
  token: {token}
"""

AUTO_ATTACH_DISABLED = """\
#cloud-config
apt:
  ppa:ua-client/daily
ubuntu_advantage:
  disable_auto_attach: true
"""

AUTO_ATTACH_CUSTOM_SERVICES = """\
ubuntu_advantage:
enable:
- fips
enable_beta:
- realtime-kernel
"""


AUTO_ATTACH_DISABLED_SERVICES = """\
ubuntu_advantage:
enable: []
enable_beta: []
"""


def did_ua_service_noop(client: IntegrationInstance) -> bool:
    """Determine if ua.service did run or not"""
    raise NotImplementedError("TODO")


@pytest.mark.ubuntu
@pytest.mark.ci
class TestUbuntuAdvantage:
    @pytest.mark.user_data(ATTACH_FALLBACK.format(token=UA_TOKEN_VALID))
    @pytest.mark.skip(reason="TODO: Add `UA_TOKEN_VALID` as secret")
    def test_valid_token(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        status = client.execute("ua status")
        assert status.ok
        assert "This machine is not attached" not in status.stdout

    @pytest.mark.user_data(ATTACH_FALLBACK.format(token="<invalid_token>"))
    def test_invalid_token(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Failure attaching Ubuntu Advantage:" in log
        assert "Stderr: Invalid token. See https://ubuntu.com/advantage" in log
        status = client.execute("ua status")
        assert status.ok
        assert "This machine is not attached" in status.stdout


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

    @pytest.mark.user_data(AUTO_ATTACH_CUSTOM_SERVICES)
    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_custom_services(
        self, client: IntegrationInstance
    ):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)
        # TODO check that cc_ubuntu_advantage did auto-attach properly
        # TODO check only fips and realtime-kernel are enabled

    @pytest.mark.user_data(AUTO_ATTACH_DISABLED_SERVICES)
    @pytest.mark.skip(reason="TODO")
    def test_ubuntu_advantage_disabled_services(
        self, client: IntegrationInstance
    ):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert did_ua_service_noop(client)
        # TODO check that cc_ubuntu_advantage did auto-attach properly
        # TODO check all services are disabled
