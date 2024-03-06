"""Integration tests for LXD bridge creation.

(This is ported from
``tests/cloud_tests/testcases/modules/lxd_bridge.yaml``.)
"""
import warnings

import pytest
import yaml

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import verify_clean_log

BRIDGE_USER_DATA = """\
#cloud-config
lxd:
  init:
    storage_backend: btrfs
  bridge:
    mode: new
    name: lxdbr0
    ipv4_address: 10.100.100.1
    ipv4_netmask: 24
    ipv4_dhcp_first: 10.100.100.100
    ipv4_dhcp_last: 10.100.100.200
    ipv4_nat: true
    domain: lxd
    mtu: 9000
"""

STORAGE_USER_DATA = """\
#cloud-config
lxd:
  init:
    storage_backend: {}
"""

PRESEED_USER_DATA = """\
#cloud-config
lxd:
  preseed: |
    config: {}
    networks:
    - config:
        ipv4.address: auto
        ipv6.address: auto
      description: ""
      name: lxdbr0
      type: ""
    storage_pools:
    - config:
        source: /var/snap/lxd/common/lxd/storage-pools/default
      description: ""
      name: default
      driver: dir
    profiles:
    - config: {}
      description: ""
      devices:
        eth0:
          name: eth0
          nictype: bridged
          parent: lxdbr0
          type: nic
        root:
          path: /
          pool: default
          type: disk
      name: default
    cluster: null
"""


STORAGE_PRESEED_USER_DATA = """\
#cloud-config
lxd:
  preseed: |
    networks:
    - config:
        ipv4.address: 10.42.42.1/24
        ipv4.nat: "true"
        ipv6.address: fd42:4242:4242:4242::1/64
        ipv6.nat: "true"
      description: ""
      name: lxdbr0
      type: bridge
      project: default
    storage_pools:
    - config:
        size: 5GiB
        source: /var/snap/lxd/common/lxd/disks/default.img
      description: ""
      name: default
      driver: {driver}
    profiles:
    - config: {{ }}
      description: Default LXD profile
      devices:
        eth0:
          {nictype}
          {parent}
          {network}
          type: nic
        root:
          path: /
          pool: default
          type: disk
      name: default
    - config:
        user.vendor-data: |
          #cloud-config
          write_files:
          - path: /var/lib/cloud/scripts/per-once/setup-lxc.sh
            encoding: b64
            permissions: '0755'
            owner: root:root
            content: |
              IyEvYmluL2Jhc2gKZWNobyBZRVAgPj4gL3Zhci9sb2cvY2xvdWQtaW5pdC5sb2cK
      devices:
        config:
          source: cloud-init:config
          type: disk
        eth0:
          name: eth0
          network: lxdbr0
          type: nic
        root:
          path: /
          pool: default
          type: disk
      description: Pycloudlib LXD profile for bionic VMs
      name: bionic-vm-lxc-setup
    projects:
    - config:
        features.images: "true"
        features.networks: "true"
        features.profiles: "true"
        features.storage.volumes: "true"
      description: Default LXD project
      name: default
    - config:
        features.images: "false"
        features.networks: "true"
        features.profiles: "false"
        features.storage.volumes: "true"
      description: Limited project
      name: limited
"""


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot run LXD"
)
@pytest.mark.user_data(BRIDGE_USER_DATA)
class TestLxdBridge:
    @pytest.mark.parametrize("binary_name", ["lxc", "lxd"])
    def test_binaries_installed(self, class_client, binary_name):
        """Check that the expected LXD binaries are installed"""
        assert class_client.execute(["which", binary_name]).ok

    def test_bridge(self, class_client):
        """Check that the given bridge is configured"""
        cloud_init_log = class_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(cloud_init_log)

        # The bridge should exist
        assert class_client.execute("ip addr show lxdbr0").ok

        raw_network_config = class_client.execute("lxc network show lxdbr0")
        network_config = yaml.safe_load(raw_network_config)
        assert "10.100.100.1/24" == network_config["config"]["ipv4.address"]


def validate_storage(validate_client, pkg_name, command):
    log = validate_client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log, ignore_deprecations=False)
    return log


def validate_preseed_profiles(client, preseed_cfg):
    for src_profile in preseed_cfg["profiles"]:
        profile = yaml.safe_load(
            client.execute(f"lxc profile show {src_profile['name']}")
        )
        assert src_profile["config"] == profile["config"]


def validate_preseed_storage_pools(client, preseed_cfg):
    for src_storage in preseed_cfg["storage_pools"]:
        storage_pool = yaml.safe_load(
            client.execute(f"lxc storage show {src_storage['name']}")
        )
        if "volatile.initial_source" in storage_pool["config"]:
            assert storage_pool["config"]["source"] == storage_pool[
                "config"
            ].pop("volatile.initial_source")
        if storage_pool["driver"] == "zfs":
            "default" == storage_pool["config"].pop("zfs.pool_name")
        assert storage_pool["config"] == src_storage["config"]
        assert storage_pool["driver"] == src_storage["driver"]


def validate_preseed_projects(client: IntegrationInstance, preseed_cfg):
    # Support for projects by lxd init --preseed was added in lxd 4.12
    # https://github.com/canonical/lxd/releases/tag/lxd-4.12
    if CURRENT_RELEASE.series in ("bionic", "focal"):
        return
    for src_project in preseed_cfg.get("projects", []):
        proj_name = src_project["name"]
        proj_result = client.execute(f"lxc project show {proj_name}")
        assert (
            proj_result.ok
        ), f"Error showing `{proj_name}` project info: {proj_result.stderr}"
        project = yaml.safe_load(
            client.execute(f"lxc project show {src_project['name']}")
        )
        project.pop("used_by", None)

        # `features.storage.buckets` was introduced in lxd 5.5. More info:
        # https://github.com/canonical/lxd/releases/tag/lxd-5.5
        if "features.storage.buckets" in project["config"]:
            assert "true" == project["config"].pop("features.storage.buckets")
        # `features.networks.zones` was introduced in lxd 5.9. More info:
        # https://github.com/canonical/lxd/releases/tag/lxd-5.9
        if "features.networks.zones" in project["config"]:
            assert "true" == project["config"].pop("features.networks.zones")
        assert project == src_project


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot manipulate storage"
)
@pytest.mark.user_data(STORAGE_USER_DATA.format("btrfs"))
def test_storage_btrfs(client):
    validate_storage(client, "btrfs-progs", "mkfs.btrfs")


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot manipulate LXD"
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL, reason="tested on Focal and later"
)
def test_storage_preseed_btrfs(setup_image, session_cloud: IntegrationCloud):
    # TODO: If test is marked as not bionic, why is there a bionic section?
    if CURRENT_RELEASE.series in ("bionic",):
        nictype = "nictype: bridged"
        parent = "parent: lxdbr0"
        network = ""
    else:
        nictype = ""
        parent = ""
        network = "network: lxdbr0"
    user_data = STORAGE_PRESEED_USER_DATA.format(
        driver="btrfs", nictype=nictype, parent=parent, network=network
    )
    with session_cloud.launch(user_data=user_data) as client:
        validate_storage(client, "btrfs-progs", "mkfs.btrfs")
        src_cfg = yaml.safe_load(user_data)
        preseed_cfg = yaml.safe_load(src_cfg["lxd"]["preseed"])
        validate_preseed_profiles(client, preseed_cfg)
        validate_preseed_storage_pools(client, preseed_cfg)
        validate_preseed_projects(client, preseed_cfg)


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot manipulate LVM"
)
@pytest.mark.user_data(STORAGE_USER_DATA.format("lvm"))
def test_storage_lvm(client):
    log = client.read_from_file("/var/log/cloud-init.log")

    # Note to self
    if (
        "doesn't use thinpool by default on Ubuntu due to LP" not in log
        and "-kvm" not in client.execute("uname -r")
    ):
        warnings.warn("LP 1982780 has been fixed, update to allow thinpools")
    validate_storage(client, "lvm2", "lvcreate")


@pytest.mark.user_data(PRESEED_USER_DATA)
def test_basic_preseed(client):
    preseed_cfg = yaml.safe_load(PRESEED_USER_DATA)["lxd"]["preseed"]
    preseed_cfg = yaml.safe_load(preseed_cfg)
    cloud_init_log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(cloud_init_log)
    validate_preseed_profiles(client, preseed_cfg)
    validate_preseed_storage_pools(client, preseed_cfg)
    validate_preseed_projects(client, preseed_cfg)


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot manipulate ZFS"
)
@pytest.mark.user_data(STORAGE_USER_DATA.format("zfs"))
def test_storage_zfs(client):
    validate_storage(client, "zfsutils-linux", "zpool")


@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot manipulate LXD"
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL, reason="Tested on focal and later"
)
def test_storage_preseed_zfs(setup_image, session_cloud: IntegrationCloud):
    # TODO: If test is marked as not bionic, why is there a bionic section?
    if CURRENT_RELEASE.series in ("bionic",):
        nictype = "nictype: bridged"
        parent = "parent: lxdbr0"
        network = ""
    else:
        nictype = ""
        parent = ""
        network = "network: lxdbr0"
    user_data = STORAGE_PRESEED_USER_DATA.format(
        driver="zfs", nictype=nictype, parent=parent, network=network
    )
    with session_cloud.launch(user_data=user_data) as client:
        validate_storage(client, "zfsutils-linux", "zpool")
        src_cfg = yaml.safe_load(user_data)
        preseed_cfg = yaml.safe_load(src_cfg["lxd"]["preseed"])
        validate_preseed_profiles(client, preseed_cfg)
        validate_preseed_storage_pools(client, preseed_cfg)
        validate_preseed_projects(client, preseed_cfg)
