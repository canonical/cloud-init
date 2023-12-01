"""DataSourceNone integration tests on LXD."""
import json

from pycloudlib.lxd.instance import LXDInstance

from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

DS_NONE_BASE_CFG = """\
datasource_list: [None]
datasource:
  None:
    metadata:
      instance-id: my-iid-uuid
    userdata_raw: |
      #cloud-config
      runcmd:
      - touch /var/tmp/success-with-datasource-none
"""


@retry(tries=90, delay=1)
def wait_for_cloud_init_status_file(instance: LXDInstance):
    """Wait for a non-empty status.json indicating cloud-init has started.

    We don't wait for cloud-init to complete in this scenario as the failure
    path on some images leaves us with cloud-init status blocking
    indefinitely in the "running" state.
    """
    status_file = instance.read_from_file("/run/cloud-init/status.json")
    assert len(status_file)


def test_datasource_none_discovery(client: IntegrationInstance):
    """Integration test for #4635.

    Test that DataSourceNone detection (used by live installers) doesn't
    generate errors or warnings.
    """
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    # Limit datasource detection to DataSourceNone.
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-force-dsnone.cfg", DS_NONE_BASE_CFG
    )
    if client.settings.PLATFORM in ["lxd_container"]:
        # DataSourceNone provides no network_config.
        # To avoid changing network config from platform desired net cfg
        # to fallback config, copy out the rendered network config
        # to /etc/cloud/cloud.cfg.d/99-orig-net.cfg so it is
        # setup by the DataSourceNone case as well.
        # Otherwise (LXD specifically) we'll have network torn down due
        # to virtual NICs present which results in not network being
        # brought up when we emit fallback config which attempts to
        # match on PermanentMACAddress. LP:#2022947
        client.execute(
            "cp /etc/netplan/50-cloud-init.yaml"
            " /etc/cloud/cloud.cfg.d/99-orig-net.cfg"
        )
    client.execute("cloud-init clean --logs --reboot")
    wait_for_cloud_init_status_file(client)
    status = json.loads(client.execute("cloud-init status --format=json"))
    assert [] == status["errors"]
    expected_warnings = [
        "Used fallback datasource",
        "Falling back to a hard restart of systemd-networkd.service",
    ]
    unexpected_warnings = []
    for current_warning in status["recoverable_errors"].get("WARNING", []):
        if [w for w in expected_warnings if w in current_warning]:
            # Found a matching expected_warning substring in current_warning
            continue
        unexpected_warnings.append(current_warning)

    if unexpected_warnings:
        raise AssertionError(
            f"Unexpected recoverable errors: {list(unexpected_warnings)}"
        )
    client.execute("cloud-init status --wait")
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert client.execute("test -f /var/tmp/success-with-datasource-none").ok
