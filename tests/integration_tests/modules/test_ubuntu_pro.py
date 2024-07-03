import json
import logging
import os

import pytest
from pycloudlib.cloud import ImageType

from cloudinit.util import should_log_deprecation
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import (
    CloudInitSource,
    IntegrationInstance,
)
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import (
    BIONIC,
    CURRENT_RELEASE,
    FOCAL,
    IS_UBUNTU,
    JAMMY,
)
from tests.integration_tests.util import (
    get_feature_flag_value,
    verify_clean_log,
)

LOG = logging.getLogger("integration_testing.test_ubuntu_pro")

CLOUD_INIT_UA_TOKEN = os.environ.get("CLOUD_INIT_UA_TOKEN")

ATTACH_FALLBACK = """\
#cloud-config
ubuntu_pro:
  features:
    disable_auto_attach: true
  token: {token}
"""

ATTACH = """\
#cloud-config
ubuntu_pro:
  token: {token}
  enable:
  - esm-infra
"""

PRO_AUTO_ATTACH_DISABLED = """\
#cloud-config
ubuntu_pro:
  features:
    disable_auto_attach: true
"""

PRO_DAEMON_DISABLED = """\
#cloud-config
# Disable Pro daemon (only needed in GCE)
ubuntu_pro:
  features:
    disable_auto_attach: true
bootcmd:
- sudo systemctl mask ubuntu-advantage.service
"""

AUTO_ATTACH_CUSTOM_SERVICES = """\
#cloud-config
ubuntu_pro:
  enable:
  - esm-infra
"""


def assert_ua_service_noop(client: IntegrationInstance):
    status_resp = client.execute("systemctl status ua-auto-attach.service")
    assert status_resp.return_code == 3  # Due to being skipped
    assert (
        "Skipping auto-attach and deferring to cloud-init to setup and"
        " configure auto-attach" in status_resp.stdout
    )


def is_attached(client: IntegrationInstance) -> bool:
    status_resp = client.execute("sudo pro status --format json")
    assert status_resp.ok
    status = json.loads(status_resp.stdout)
    return bool(status.get("attached"))


def get_services_status(client: IntegrationInstance) -> dict:
    """Creates a map of service -> is_enable.

    pro status --format json contains a key with list of service objects like:

    {
      ...
      "services":[
        {
          "available":"yes",
          "blocked_by":[

          ],
          "description":"Common Criteria EAL2 Provisioning Packages",
          "description_override":null,
          "entitled":"yes",
          "name":"cc-eal",
          "status":"disabled",
          "status_details":"CC EAL2 is not configured"
        },
        ...
      ]
    }

    :return: Dict where the keys are ua service names and the values
    are booleans representing if the service is enable or not.
    """
    status_resp = client.execute("sudo pro status --format json")
    assert status_resp.ok
    status = json.loads(status_resp.stdout)
    return {
        svc["name"]: svc["status"] in ("enabled", "warning")
        for svc in status["services"]
    }


@pytest.mark.adhoc
@pytest.mark.skipif(not IS_UBUNTU, reason="Test is Ubuntu specific")
@pytest.mark.skipif(
    not CLOUD_INIT_UA_TOKEN, reason="CLOUD_INIT_UA_TOKEN env var not provided"
)
class TestUbuntuAdvantage:
    @pytest.mark.user_data(ATTACH_FALLBACK.format(token=CLOUD_INIT_UA_TOKEN))
    def test_valid_token(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert is_attached(client)
        client.execute("pro detach")
        # Replace ubuntu_pro with previously named ubuntu_advantage
        client.execute(
            "sed -i 's/ubuntu_pro$/ubuntu_advantage/' /etc/cloud/cloud.cfg"
        )
        client.restart()
        version_boundary = get_feature_flag_value(
            client, "DEPRECATION_INFO_BOUNDARY"
        )
        # ubuntu_advantage key is deprecated in version 24.1
        if should_log_deprecation("24.1", version_boundary):
            log_level = "DEPRECATED"
        else:
            log_level = "INFO"
        client.execute(
            rf"grep \"{log_level}]: Module has been renamed from"
            " cc_ubuntu_advantage to cc_ubuntu_pro /var/log/cloud-init.log"
        ).ok
        assert is_attached(client)

    @pytest.mark.user_data(ATTACH.format(token=CLOUD_INIT_UA_TOKEN))
    def test_idempotency(self, client: IntegrationInstance):
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert is_attached(client)

        # Clean reboot to change instance-id and trigger cc_ua in next boot
        assert client.execute("cloud-init clean --logs").ok
        client.restart()

        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert is_attached(client)

        # Assert service-already-enabled handling for esm-infra.
        # First totally destroy ubuntu-advantage-tools data and state.
        # This is a hack but results in a system that thinks it
        # is detached even though esm-infra is still enabled.
        # When cloud-init runs again, it will successfully re-attach
        # and then notice that esm-infra is already enabled.
        client.execute("rm -rf /var/lib/ubuntu-advantage")
        assert client.execute("cloud-init clean --logs").ok
        client.restart()
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert "Service `esm-infra` already enabled" in log


def maybe_install_cloud_init(session_cloud: IntegrationCloud):
    source = get_validated_source(session_cloud)

    launch_kwargs = {
        "image_id": session_cloud.cloud_instance.daily_image(
            CURRENT_RELEASE.series, image_type=ImageType.PRO
        )
    }

    if source is CloudInitSource.NONE:
        LOG.info(
            "No need to customize cloud-init version. Return without spawning"
            " an extra instance"
        )
        return launch_kwargs

    user_data = (
        PRO_DAEMON_DISABLED
        if session_cloud.settings.PLATFORM == "gce"
        else PRO_AUTO_ATTACH_DISABLED
    )

    with session_cloud.launch(
        user_data=user_data,
        launch_kwargs=launch_kwargs,
    ) as client:
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)

        assert not is_attached(
            client
        ), "Test precondition error. Instance is auto-attached."

        if session_cloud.settings.PLATFORM == "gce":
            LOG.info(
                "Restore `ubuntu-advantage.service` original status for next"
                " boot"
            )
            assert client.execute(
                "sudo systemctl unmask ubuntu-advantage.service"
            ).ok

        client.install_new_cloud_init(source)
        session_cloud.snapshot_id = client.snapshot()
        client.destroy()

    return {"image_id": session_cloud.snapshot_id}


@pytest.mark.skipif(
    not all([IS_UBUNTU, CURRENT_RELEASE in [BIONIC, FOCAL, JAMMY]]),
    reason="Test runs on Ubuntu LTS releases only",
)
@pytest.mark.skipif(
    PLATFORM not in ["azure", "ec2", "gce"],
    reason=f"Pro isn't offered on {PLATFORM}.",
)
class TestUbuntuAdvantagePro:
    def test_custom_services(self, session_cloud: IntegrationCloud):
        launch_kwargs = maybe_install_cloud_init(session_cloud)
        with session_cloud.launch(
            user_data=AUTO_ATTACH_CUSTOM_SERVICES,
            launch_kwargs=launch_kwargs,
        ) as client:
            log = client.read_from_file("/var/log/cloud-init.log")
            verify_clean_log(log)
            assert_ua_service_noop(client)
            assert is_attached(client)
            services_status = get_services_status(client)
            assert services_status.pop(
                "esm-infra"
            ), "esm-infra expected to be enabled"
            enabled_services = {
                svc for svc, status in services_status.items() if status
            }
            assert (
                not enabled_services
            ), f"Only livepatch must be enabled. Found: {enabled_services}"
