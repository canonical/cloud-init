import json

import pytest
import yaml

from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log


def _customize_envionment(client: IntegrationInstance):
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-detect-lxd.cfg",
        "datasource_list: [LXD]\n",
    )
    client.execute("cloud-init clean --logs")
    client.restart()


# This test should be able to work on any cloud whose datasource specifies
# a NETWORK dependency
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
@pytest.mark.ubuntu  # Because netplan
def test_lxd_datasource_discovery(client: IntegrationInstance):
    """Test that DataSourceLXD is detected instead of NoCloud."""
    _customize_envionment(client)
    nic_dev = "enp5s0" if client.settings.PLATFORM == "lxd_vm" else "eth0"
    result = client.execute("cloud-init status --long")
    if not result.ok:
        raise AssertionError("cloud-init failed:\n%s", result.stderr)
    if "DataSourceLXD" not in result.stdout:
        raise AssertionError(
            "cloud-init did not discover DataSourceLXD", result.stdout
        )
    netplan_yaml = client.execute("cat /etc/netplan/50-cloud-init.yaml")
    netplan_cfg = yaml.safe_load(netplan_yaml)
    assert {
        "network": {"ethernets": {nic_dev: {"dhcp4": True}}, "version": 2}
    } == netplan_cfg
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
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
    assert ["_doc", "_metadata_api_version", "config", "meta-data"] == sorted(
        list(ds_cfg.keys())
    )
    if (
        client.settings.PLATFORM == "lxd_vm"
        and ImageSpecification.from_os_image().release == "bionic"
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
    assert "#cloud-config\ninstance-id" in ds_cfg["meta-data"]
    # Assert NoCloud seed data is still present in cloud image metadata
    # This will start failing if we redact metadata templates from
    # https://cloud-images.ubuntu.com/daily/server/jammy/current/\
    #    jammy-server-cloudimg-amd64-lxd.tar.xz
    nocloud_metadata = yaml.safe_load(
        client.read_from_file("/var/lib/cloud/seed/nocloud-net/meta-data")
    )
    assert client.instance.name == nocloud_metadata["instance-id"]
    assert (
        nocloud_metadata["instance-id"] == nocloud_metadata["local-hostname"]
    )
    assert v1["public_ssh_keys"][0] == nocloud_metadata["public-keys"]
