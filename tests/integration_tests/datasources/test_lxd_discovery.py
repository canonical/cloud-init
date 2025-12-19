import json

import pytest
import yaml

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE
from tests.integration_tests.util import (
    lxd_has_nocloud,
    verify_clean_boot,
    verify_clean_log,
    wait_for_cloud_init,
)


def _customize_environment(client: IntegrationInstance):
    # Assert our platform can detect LXD during systemd generator timeframe.
    ds_id_log = client.execute("cat /run/cloud-init/ds-identify.log").stdout
    assert "check for 'LXD' returned found" in ds_id_log

    if client.settings.PLATFORM == "lxd_vm":
        # ds-identify runs at systemd generator time before /dev/lxd/sock.
        # Assert we can expected virtio-ports artifacts which indicates LXD is
        # viable.
        result = client.execute("cat /sys/class/virtio-ports/*/name")
        if not result.ok:
            raise AssertionError(
                "Missing expected /sys/class/virtio-ports/*/name"
            )
        if "LXD" != result.stdout:
            raise AssertionError(
                f"virtio-ports not LXD serial devices: {result.stdout}"
            )

    # Having multiple datasources prevents ds-identify from short-circuiting
    # detection logic with a log like:
    #     single entry in datasource_list (LXD) use that.
    # Also, NoCloud is detected during init-local timeframe.

    # If there is a race on VMs where /dev/lxd/sock is not setup in init-local
    # cloud-init will fallback to NoCloud and fail this test.
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-detect-lxd-first.cfg",
        "datasource_list: [LXD, NoCloud]\n",
    )
    # This is also to ensure that NoCloud can be detected
    if CURRENT_RELEASE.series == "jammy":
        # Add nocloud-net seed files because Jammy no longer delivers NoCloud
        # (LP: #1958460).
        client.execute("mkdir -p /var/lib/cloud/seed/nocloud-net")
        client.write_to_file("/var/lib/cloud/seed/nocloud-net/meta-data", "")
        client.write_to_file(
            "/var/lib/cloud/seed/nocloud-net/user-data", "#cloud-config\n{}"
        )
    client.execute("cloud-init clean --logs")
    client.restart()


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Test is LXD KVM specific")
def test_lxd_kvm_datasource_discovery_without_lxd_socket(
    session_cloud: IntegrationCloud,
):
    """Test DataSourceLXD is detected on KVM by virtio-ports."""
    with session_cloud.launch(
        wait=False,  # to prevent cloud-init status --wait
        launch_kwargs={
            # We detect the LXD datasource using a socket available to the
            # container. This prevents the socket from being exposed in the
            # container, so LXD will not be detected.
            # This allows us to wait for detection in 'init' stage with
            # DataSourceNoCloudNet.
            "config_dict": {"security.devlxd": False},
        },
    ) as client:
        _customize_environment(client)
        # We know this will be an LXD instance due to our pytest mark
        client.instance.execute_via_ssh = False  # pyright: ignore
        result = wait_for_cloud_init(client, num_retries=60)
        if not result.ok:
            raise AssertionError("cloud-init failed:\n%s", result.stderr)
        if "DataSourceLXD" not in result.stdout:
            raise AssertionError(
                "cloud-init did not discover DataSourceLXD", result.stdout
            )


@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason="Test is LXD specific",
)
def test_lxd_datasource_discovery(client: IntegrationInstance):
    """Test that DataSourceLXD is detected instead of NoCloud."""

    _customize_environment(client)
    result = client.execute("cloud-init status --wait --long")
    if not result.ok:
        raise AssertionError("cloud-init failed:\n%s", result.stderr)
    if "DataSourceLXD" not in result.stdout:
        raise AssertionError(
            "cloud-init did not discover DataSourceLXD", result.stdout
        )
    netplan_yaml = client.execute("cat /etc/netplan/50-cloud-init.yaml")
    netplan_cfg = yaml.safe_load(netplan_yaml)

    platform = client.settings.PLATFORM
    nic_dev = "eth0" if platform == "lxd_container" else "enp5s0"
    assert {
        "network": {"ethernets": {nic_dev: {"dhcp4": True}}, "version": 2}
    } == netplan_cfg
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    verify_clean_boot(client)
    result = client.execute("cloud-id")
    if result.stdout != "lxd":
        raise AssertionError(
            "cloud-id didn't report lxd. Result: %s", result.stdout
        )
    # Validate config instance data represented
    data = json.loads(
        client.read_from_file("/run/cloud-init/instance-data.json")
    )
    v1 = data["v1"]
    ds_cfg = data["ds"]
    assert "lxd" == v1["platform"]
    assert "LXD socket API v. 1.0 (/dev/lxd/sock)" == v1["subplatform"]
    ds_cfg = json.loads(client.execute("cloud-init query ds").stdout)
    assert [
        "_doc",
        "_metadata_api_version",
        "config",
        "devices",
        "meta-data",
    ] == sorted(list(ds_cfg.keys()))
    if (
        client.settings.PLATFORM == "lxd_vm"
        and CURRENT_RELEASE.series == "bionic"
    ):
        # pycloudlib injects user.vendor_data for lxd_vm on bionic
        # to start the lxd-agent.
        # https://github.com/canonical/pycloudlib/blob/main/pycloudlib/\
        #    lxd/defaults.py#L13-L27
        # Underscore-delimited aliases exist for any keys containing hyphens or
        # dots.
        lxd_config_keys = ["user.meta-data", "user.vendor-data"]
    else:
        lxd_config_keys = ["user.meta-data"]
    assert "1.0" == ds_cfg["_metadata_api_version"]
    assert lxd_config_keys == list(ds_cfg["config"].keys())
    assert {"public-keys": v1["public_ssh_keys"][0]} == (
        yaml.safe_load(ds_cfg["config"]["user.meta-data"])
    )
    assert "instance-id" in ds_cfg["meta-data"]

    # Some series no longer provide nocloud-net seed files (LP: #1958460)
    if lxd_has_nocloud(client):
        # Assert NoCloud seed files are still present in non-Jammy images
        # and that NoCloud seed files provide the same content as LXD socket.
        nocloud_metadata = yaml.safe_load(
            client.read_from_file("/var/lib/cloud/seed/nocloud-net/meta-data")
        )
        assert client.instance.name == nocloud_metadata["instance-id"]
        assert (
            nocloud_metadata["instance-id"]
            == nocloud_metadata["local-hostname"]
        )
        assert v1["public_ssh_keys"][0] == nocloud_metadata["public-keys"]
