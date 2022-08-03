import os

import pytest
from pycloudlib.cloud import ImageType

from tests.integration_tests.clouds import IntegrationCloud
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

UA_DAILY = """\
#cloud-config
apt:
  sources:
    ua-daily:
      source: 'ppa:ua-client/daily'
package_update: true
package_upgrade: true
packages:
- ubuntu-advantage-tools
"""

AUTO_ATTACH_CUSTOM_SERVICES = """\
#cloud-config
ubuntu_advantage:
  enable:
  - fips
  enable_beta:
  - realtime-kernel
"""


AUTO_ATTACH_DISABLED_SERVICES = """\
#cloud-config
ubuntu_advantage:
  enable: []
  enable_beta: []
"""


def did_ua_service_noop(client: IntegrationInstance):
    """Determine if ua.service did run or not"""
    ua_log = client.read_from_file("/var/log/ubuntu-advantage.log")
    assert (
        '"should_auto_attach": true'
        in client.execute(
            "pro api u.pro.attach.auto.should_auto_attach.v1"
        ).stdout
    )
    assert (
        "Skipping auto-attach and deferring to cloud-init to setup and"
        " configure auto-attach" in ua_log
    )


def is_auto_attached(client: IntegrationInstance):
    assert (
        "machine is attached to an Ubuntu Pro subscription."
        in client.execute("pro status").stdout
    )


@pytest.mark.ubuntu
@pytest.mark.adhoc
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


@pytest.fixture
def ua_daily_session_cloud(session_cloud: IntegrationCloud, setup_image):
    # We install here `ubuntu-advantage-tools` for ppa:ua-client/daily
    # TODO remove this fixture completely after UA releases a new version
    # containing the 'uaclient.api.u.pro.attach.auto.full_auto_attach.v1' api
    # endpoint
    old_snapshot_id = session_cloud.snapshot_id
    with session_cloud.launch(user_data=UA_DAILY) as client:
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        old_boot_id = client.instance.get_boot_id()
        client.execute("cloud-init clean --logs --reboot")
        client.instance._wait_for_execute(old_boot_id=old_boot_id)
        session_cloud.snapshot_id = client.snapshot()

    yield session_cloud

    try:
        session_cloud.delete_snapshot()
    finally:
        session_cloud.snapshot_id = old_snapshot_id


@pytest.mark.integration_cloud_args(image_type=ImageType.PRO)
@pytest.mark.azure
@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.ubuntu
@pytest.mark.adhoc
class TestUbuntuAdvantagePro:
    def test_ubuntu_advantage_disabled_services(
        self, ua_daily_session_cloud: IntegrationCloud, setup_image
    ):
        with ua_daily_session_cloud.launch(
            user_data=AUTO_ATTACH_DISABLED_SERVICES,
            launch_kwargs={
                "image_id": ua_daily_session_cloud.snapshot_id,
            },
        ) as client:
            log = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log)
            did_ua_service_noop(client)
            is_auto_attached(client)
            # TODO check all services are disabled

    def test_ubuntu_advantage_disabled_services_cloud_cfg(
        self, ua_daily_session_cloud: IntegrationCloud, setup_image
    ):
        with ua_daily_session_cloud.launch(
            launch_kwargs={
                "image_id": ua_daily_session_cloud.snapshot_id,
            },
        ) as client:
            client.write_to_file(
                UA_CLOUD_CONFIG, AUTO_ATTACH_DISABLED_SERVICES
            )
            client.execute("cloud-init clean --logs --reboot")
            log = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log)
            did_ua_service_noop(client)
            is_auto_attached(client)
            # TODO check all services are disabled

    def test_ubuntu_advantage_custom_services(
        self, ua_daily_session_cloud: IntegrationCloud, setup_image
    ):
        with ua_daily_session_cloud.launch(
            user_data=AUTO_ATTACH_CUSTOM_SERVICES,
            launch_kwargs={
                "image_id": ua_daily_session_cloud.snapshot_id,
            },
        ) as client:
            log = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log)
            did_ua_service_noop(client)
            is_auto_attached(client)
            # TODO check only fips and realtime-kernel are enabled
