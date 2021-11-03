# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
from copy import deepcopy
import stat
from unittest import mock
import yaml

import pytest

from cloudinit.sources import DataSourceLXD as lxd, UNSET
DS_PATH = "cloudinit.sources.DataSourceLXD."


LStatResponse = namedtuple("lstatresponse", "st_mode")


NETWORK_V1 = {
    "version": 1,
    "config": [
        {
            "type": "physical", "name": "eth0",
            "subnets": [{"type": "dhcp", "control": "auto"}]
        }
    ]
}
NETWORK_V1_MANUAL = deepcopy(NETWORK_V1)
NETWORK_V1_MANUAL["config"][0]["subnets"][0]["control"] = "manual"


def _add_network_v1_device(devname) -> dict:
    """Helper to inject device name into default network v1 config."""
    network_cfg = deepcopy(NETWORK_V1)
    network_cfg["config"][0]["name"] = devname
    return network_cfg


LXD_V1_METADATA = {
    "meta-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
    "network-config": NETWORK_V1,
    "user-data": "#cloud-config\npackages: [sl]\n",
    "vendor-data": "#cloud-config\nruncmd: ['echo vendor-data']\n",
    "1.0": {
        "meta-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
        "config": {
            "user.user-data":
                "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
            "user.vendor-data":
                "#cloud-config\nruncmd: ['echo vendor-data']\n",
            "user.network-config": yaml.safe_dump(NETWORK_V1),
        }
    }
}


@pytest.fixture
def lxd_metadata():
    return LXD_V1_METADATA


@pytest.yield_fixture
def lxd_ds(request, paths, lxd_metadata):
    """
    Return an instantiated DataSourceLXD.

    This also performs the mocking required for the default test case:
        * ``is_platform_viable`` returns True,
        * ``read_metadata`` returns ``LXD_V1_METADATA``

    (This uses the paths fixture for the required helpers.Paths object)
    """
    with mock.patch(DS_PATH + "is_platform_viable", return_value=True):
        with mock.patch(DS_PATH + "read_metadata", return_value=lxd_metadata):
            yield lxd.DataSourceLXD(
                sys_cfg={}, distro=mock.Mock(), paths=paths
            )


class TestGenerateFallbackNetworkConfig:

    @pytest.mark.parametrize(
        "uname_machine,systemd_detect_virt,network_mode,expected", (
            # None for systemd_detect_virt returns None from which
            ({}, None, "", NETWORK_V1),
            ({}, None, "dhcp", NETWORK_V1),
            # invalid network_mode logs warning
            ({}, None, "bogus", NETWORK_V1),
            ({}, None, "link-local", NETWORK_V1_MANUAL),
            ("anything", "lxc\n", "", NETWORK_V1),
            # `uname -m` on kvm determines devname
            ("x86_64", "kvm\n", "", _add_network_v1_device("enp5s0")),
            ("ppc64le", "kvm\n", "", _add_network_v1_device("enp0s5")),
            ("s390x", "kvm\n", "", _add_network_v1_device("enc9"))
        )
    )
    @mock.patch(DS_PATH + "util.system_info")
    @mock.patch(DS_PATH + "subp.subp")
    @mock.patch(DS_PATH + "subp.which")
    def test_net_v2_based_on_network_mode_virt_type_and_uname_machine(
        self,
        m_which,
        m_subp,
        m_system_info,
        uname_machine,
        systemd_detect_virt,
        network_mode,
        expected,
        caplog
    ):
        """Return network config v2 based on uname -m, systemd-detect-virt.

        LXC config network_mode of "link-local" will determine whether to set
        "activation-mode: manual", leaving the interface down.
        """
        if systemd_detect_virt is None:
            m_which.return_value = None
        m_system_info.return_value = {"uname": ["", "", "", "", uname_machine]}
        m_subp.return_value = (systemd_detect_virt, "")
        assert expected == lxd.generate_fallback_network_config(
            network_mode=network_mode
        )
        if systemd_detect_virt is None:
            assert 0 == m_subp.call_count
            assert 0 == m_system_info.call_count
        else:
            assert [
                mock.call(["systemd-detect-virt"])
            ] == m_subp.call_args_list
            if systemd_detect_virt != "kvm\n":
                assert 0 == m_system_info.call_count
            else:
                assert 1 == m_system_info.call_count
        if network_mode not in ("dhcp", "", "link-local"):
            assert "Ignoring unexpected value user.network_mode: {}".format(
                network_mode
            ) in caplog.text


class TestDataSourceLXD:
    def test_platform_info(self, lxd_ds):
        assert "LXD" == lxd_ds.dsname
        assert "lxd" == lxd_ds.cloud_name
        assert "lxd" == lxd_ds.platform_type

    def test_subplatform(self, lxd_ds):
        assert "LXD socket API v. 1.0 (/dev/lxd/sock)" == lxd_ds.subplatform

    def test__get_data(self, lxd_ds):
        """get_data calls read_metadata, setting appropiate instance attrs."""
        assert UNSET == lxd_ds._crawled_metadata
        assert UNSET == lxd_ds._network_config
        assert None is lxd_ds.userdata_raw
        assert True is lxd_ds._get_data()
        assert LXD_V1_METADATA == lxd_ds._crawled_metadata
        # network-config is dumped from YAML
        assert NETWORK_V1 == lxd_ds._network_config
        # Any user-data and vendor-data are saved as raw
        assert LXD_V1_METADATA["user-data"] == lxd_ds.userdata_raw
        assert LXD_V1_METADATA["vendor-data"] == lxd_ds.vendordata_raw


class TestIsPlatformViable:
    @pytest.mark.parametrize(
        "exists,lstat_mode,expected", (
            (False, None, False),
            (True, stat.S_IFREG, False),
            (True, stat.S_IFSOCK, True),
        )
    )
    @mock.patch(DS_PATH + "os.lstat")
    @mock.patch(DS_PATH + "os.path.exists")
    def test_expected_viable(
        self, m_exists, m_lstat, exists, lstat_mode, expected
    ):
        """Return True only when LXD_SOCKET_PATH exists and is a socket."""
        m_exists.return_value = exists
        m_lstat.return_value = LStatResponse(lstat_mode)
        assert expected is lxd.is_platform_viable()
        m_exists.assert_has_calls([mock.call(lxd.LXD_SOCKET_PATH)])
        if exists:
            m_lstat.assert_has_calls([mock.call(lxd.LXD_SOCKET_PATH)])
        else:
            assert 0 == m_lstat.call_count

# vi: ts=4 expandtab
