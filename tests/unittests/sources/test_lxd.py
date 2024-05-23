# This file is part of cloud-init. See LICENSE file for license information.

import copy
import json
import re
import stat
from collections import namedtuple
from copy import deepcopy
from unittest import mock

import pytest
import yaml

from cloudinit.sources import UNSET
from cloudinit.sources import DataSourceLXD as lxd
from cloudinit.sources import InvalidMetaDataException
from cloudinit.sources.DataSourceLXD import MetaDataKeys

DS_PATH = "cloudinit.sources.DataSourceLXD."


LStatResponse = namedtuple("LStatResponse", "st_mode")


NETWORK_V1 = {
    "version": 1,
    "config": [
        {
            "type": "physical",
            "name": "eth0",
            "subnets": [{"type": "dhcp", "control": "auto"}],
        }
    ],
}


def _add_network_v1_device(devname) -> dict:
    """Helper to inject device name into default network v1 config."""
    network_cfg: dict = deepcopy(NETWORK_V1)
    network_cfg["config"][0]["name"] = devname
    return network_cfg


LXD_V1_METADATA = {
    "meta-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
    "network-config": NETWORK_V1,
    "user-data": "#cloud-config\npackages: [sl]\n",
    "vendor-data": "#cloud-config\nruncmd: ['echo vendor-data']\n",
    "config": {
        "user.user-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
        "user.vendor-data": "#cloud-config\nruncmd: ['echo vendor-data']\n",
        "user.network-config": yaml.safe_dump(NETWORK_V1),
    },
}

LXD_V1_METADATA_NO_NETWORK_CONFIG = {
    "meta-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
    "user-data": "#cloud-config\npackages: [sl]\n",
    "vendor-data": "#cloud-config\nruncmd: ['echo vendor-data']\n",
    "config": {
        "user.user-data": "instance-id: my-lxc\nlocal-hostname: my-lxc\n\n",
        "user.vendor-data": "#cloud-config\nruncmd: ['echo vendor-data']\n",
    },
}

DEVICES = {
    "devices": {
        "some-disk": {
            "path": "/path/in/container",
            "source": "/path/on/host",
            "type": "disk",
        },
        "enp1s0": {
            "ipv4.address": "10.20.30.40",
            "name": "eth0",
            "network": "lxdbr0",
            "type": "nic",
        },
        "root": {"path": "/", "pool": "default", "type": "disk"},
        "enp1s1": {
            "ipv4.address": "10.20.30.50",
            "name": "eth1",
            "network": "lxdbr0",
            "type": "nic",
        },
    }
}


def lxd_metadata():
    return LXD_V1_METADATA


def lxd_metadata_no_network_config():
    return LXD_V1_METADATA_NO_NETWORK_CONFIG


@pytest.fixture
def lxd_ds(request, paths):
    """
    Return an instantiated DataSourceLXD.

    This also performs the mocking required for the default test case:
        * ``is_platform_viable`` returns True,
        * ``read_metadata`` returns ``LXD_V1_METADATA``

    (This uses the paths fixture for the required helpers.Paths object)
    """
    with mock.patch(DS_PATH + "is_platform_viable", return_value=True):
        with mock.patch(
            DS_PATH + "read_metadata", return_value=lxd_metadata()
        ):
            yield lxd.DataSourceLXD(
                sys_cfg={}, distro=mock.Mock(), paths=paths
            )


@pytest.fixture
def lxd_ds_no_network_config(request, paths):
    """
    Return an instantiated DataSourceLXD.

    This also performs the mocking required for the default test case:
        * ``is_platform_viable`` returns True,
        * ``read_metadata`` returns ``LXD_V1_METADATA_NO_NETWORK_CONFIG``

    (This uses the paths fixture for the required helpers.Paths object)
    """
    with mock.patch(DS_PATH + "is_platform_viable", return_value=True):
        with mock.patch(
            DS_PATH + "read_metadata",
            return_value=lxd_metadata_no_network_config(),
        ):
            yield lxd.DataSourceLXD(
                sys_cfg={}, distro=mock.Mock(), paths=paths
            )


class TestGenerateFallbackNetworkConfig:
    @pytest.mark.parametrize(
        "uname_machine,systemd_detect_virt,expected",
        (
            # None for systemd_detect_virt returns None from which
            ({}, None, NETWORK_V1),
            ({}, None, NETWORK_V1),
            ("anything", "lxc\n", NETWORK_V1),
            # `uname -m` on kvm determines devname
            ("x86_64", "kvm\n", _add_network_v1_device("enp5s0")),
            ("ppc64le", "kvm\n", _add_network_v1_device("enp0s5")),
            ("s390x", "kvm\n", _add_network_v1_device("enc9")),
        ),
    )
    @mock.patch(DS_PATH + "util.system_info")
    @mock.patch(DS_PATH + "subp.subp")
    @mock.patch(DS_PATH + "subp.which")
    @mock.patch(DS_PATH + "find_fallback_nic")
    def test_net_v2_based_on_network_mode_virt_type_and_uname_machine(
        self,
        m_fallback,
        m_which,
        m_subp,
        m_system_info,
        uname_machine,
        systemd_detect_virt,
        expected,
    ):
        """Return network config v2 based on uname -m, systemd-detect-virt."""
        m_fallback.return_value = None
        if systemd_detect_virt is None:
            m_which.return_value = None
        m_system_info.return_value = {"uname": ["", "", "", "", uname_machine]}
        m_subp.return_value = (systemd_detect_virt, "")
        assert expected == lxd.generate_network_config()
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


class TestNetworkConfig:
    @pytest.fixture(autouse=True)
    def mocks(self, mocker):
        mocker.patch(f"{DS_PATH}subp.subp", return_value=("whatever", ""))

    def test_provided_network_config(self, lxd_ds, mocker):
        def _get_data(self):
            self._crawled_metadata = copy.deepcopy(DEVICES)
            self._crawled_metadata["network-config"] = "hi"

        mocker.patch.object(
            lxd.DataSourceLXD,
            "_get_data",
            autospec=True,
            side_effect=_get_data,
        )
        assert lxd_ds.network_config == "hi"

    @pytest.mark.parametrize(
        "devices_to_remove,expected_config",
        [
            pytest.param(
                # When two nics are presented with no passed network-config,
                # Never configure more than one device.
                # Always choose lowest sorted device over higher
                # Always configure with DHCP
                [],
                {
                    "version": 1,
                    "config": [
                        {
                            "name": "eth0",
                            "subnets": [{"control": "auto", "type": "dhcp"}],
                            "type": "physical",
                        }
                    ],
                },
                id="multi-device",
            ),
            pytest.param(
                # When one device is presented, use it
                ["enp1s0"],
                {
                    "version": 1,
                    "config": [
                        {
                            "name": "eth0",
                            "subnets": [{"control": "auto", "type": "dhcp"}],
                            "type": "physical",
                        }
                    ],
                },
                id="no-eth0",
            ),
            pytest.param(
                # When one device is presented, use it
                ["enp1s1"],
                {
                    "version": 1,
                    "config": [
                        {
                            "name": "eth0",
                            "subnets": [{"control": "auto", "type": "dhcp"}],
                            "type": "physical",
                        }
                    ],
                },
                id="no-eth1",
            ),
            pytest.param(
                # When no devices are presented, generate fallback
                ["enp1s0", "enp1s1"],
                {
                    "version": 1,
                    "config": [
                        {
                            "name": "eth0",
                            "subnets": [{"control": "auto", "type": "dhcp"}],
                            "type": "physical",
                        }
                    ],
                },
                id="device-list-empty",
            ),
        ],
    )
    def test_provided_devices(
        self, devices_to_remove, expected_config, lxd_ds, mocker
    ):
        # TODO: The original point of these tests was to ensure that when
        # presented nics by the LXD devices endpoint, that we setup the correct
        # device accordingly. Once LXD provides us MAC addresses for these
        # devices, we can continue this functionality, but these tests have
        # been modified to ensure that regardless of the number of devices
        # present, we generate the proper fallback
        m_fallback = mocker.patch(
            "cloudinit.sources.DataSourceLXD.find_fallback_nic",
            return_value=None,
        )
        devices = copy.deepcopy(DEVICES)
        for name in devices_to_remove:
            del devices["devices"][name]

        def _get_data(self):
            self._crawled_metadata = devices

        mocker.patch.object(
            lxd.DataSourceLXD,
            "_get_data",
            autospec=True,
            side_effect=_get_data,
        )
        assert lxd_ds.network_config == expected_config
        assert m_fallback.call_count == 1


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

    def test_network_config_when_unset(self, lxd_ds):
        """network_config is correctly computed when _network_config and
        _crawled_metadata are unset.
        """
        assert UNSET == lxd_ds._crawled_metadata
        assert UNSET == lxd_ds._network_config
        assert None is lxd_ds.userdata_raw
        # network-config is dumped from YAML
        assert NETWORK_V1 == lxd_ds.network_config
        assert LXD_V1_METADATA == lxd_ds._crawled_metadata

    @mock.patch.object(lxd, "generate_network_config", return_value=NETWORK_V1)
    def test_network_config_crawled_metadata_no_network_config(
        self, m_generate, lxd_ds_no_network_config
    ):
        """network_config is correctly computed when _network_config is unset
        and _crawled_metadata does not contain network_config.
        """
        assert UNSET == lxd_ds_no_network_config._crawled_metadata
        assert UNSET == lxd_ds_no_network_config._network_config
        assert None is lxd_ds_no_network_config.userdata_raw
        # network-config is dumped from YAML
        assert NETWORK_V1 == lxd_ds_no_network_config.network_config
        assert (
            LXD_V1_METADATA_NO_NETWORK_CONFIG
            == lxd_ds_no_network_config._crawled_metadata
        )
        assert 1 == m_generate.call_count


class TestIsPlatformViable:
    @pytest.mark.parametrize(
        "exists,lstat_mode,expected",
        (
            (False, None, False),
            (True, stat.S_IFREG, False),
            (True, stat.S_IFSOCK, True),
        ),
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


class TestReadMetadata:
    @pytest.mark.parametrize(
        "get_devices,url_responses,expected,logs",
        (
            (  # Assert non-JSON format from config route
                False,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[NOT_JSON",
                },
                InvalidMetaDataException(
                    "Unable to process LXD config at"
                    " http://lxd/1.0/config. Expected JSON but found:"
                    " [NOT_JSON"
                ),
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                ],
            ),
            (  # Assert success on just meta-data
                False,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[]",
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {},
                    "meta-data": "local-hostname: md\n",
                },
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                ],
            ),
            (  # Assert success on devices
                True,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[]",
                    "http://lxd/1.0/devices": (
                        '{"root": {"path": "/", "pool": "default",'
                        ' "type": "disk"}}'
                    ),
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {},
                    "meta-data": "local-hostname: md\n",
                    "devices": {
                        "root": {
                            "path": "/",
                            "pool": "default",
                            "type": "disk",
                        }
                    },
                },
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                ],
            ),
            (  # Assert 404 on devices logs about skipping
                True,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[]",
                    # No devices URL response, so 404 raised
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {},
                    "meta-data": "local-hostname: md\n",
                },
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                    "Skipping http://lxd/1.0/devices on [HTTP:404]",
                ],
            ),
            (  # Assert non-JSON format from devices
                True,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[]",
                    "http://lxd/1.0/devices": '{"root"',
                },
                InvalidMetaDataException(
                    "Unable to process LXD config at"
                    ' http://lxd/1.0/devices. Expected JSON but found: {"root"'
                ),
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                ],
            ),
            (  # Assert 404s for config routes log skipping
                False,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": (
                        '["/1.0/config/user.custom1",'
                        ' "/1.0/config/user.meta-data",'
                        ' "/1.0/config/user.network-config",'
                        ' "/1.0/config/user.user-data",'
                        ' "/1.0/config/user.vendor-data"]'
                    ),
                    "http://lxd/1.0/config/user.custom1": "custom1",
                    "http://lxd/1.0/config/user.meta-data": "",  # 404
                    "http://lxd/1.0/config/user.network-config": "net-config",
                    "http://lxd/1.0/config/user.user-data": "",  # 404
                    "http://lxd/1.0/config/user.vendor-data": "",  # 404
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {
                        "user.custom1": "custom1",  # Not promoted
                        "user.network-config": "net-config",
                    },
                    "meta-data": "local-hostname: md\n",
                    "network-config": "net-config",
                },
                [
                    "Skipping http://lxd/1.0/config/user.vendor-data on"
                    " [HTTP:404]",
                    "Skipping http://lxd/1.0/config/user.meta-data on"
                    " [HTTP:404]",
                    "Skipping http://lxd/1.0/config/user.user-data on"
                    " [HTTP:404]",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.custom1",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/user.network-config",
                ],
            ),
            (  # Assert all CONFIG_KEY_ALIASES promoted to top-level keys
                False,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": (
                        '["/1.0/config/user.custom1",'
                        ' "/1.0/config/user.meta-data",'
                        ' "/1.0/config/user.network-config",'
                        ' "/1.0/config/user.user-data",'
                        ' "/1.0/config/user.vendor-data"]'
                    ),
                    "http://lxd/1.0/config/user.custom1": "custom1",
                    "http://lxd/1.0/config/user.meta-data": "meta-data",
                    "http://lxd/1.0/config/user.network-config": "net-config",
                    "http://lxd/1.0/config/user.user-data": "user-data",
                    "http://lxd/1.0/config/user.vendor-data": "vendor-data",
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {
                        "user.custom1": "custom1",  # Not promoted
                        "user.meta-data": "meta-data",
                        "user.network-config": "net-config",
                        "user.user-data": "user-data",
                        "user.vendor-data": "vendor-data",
                    },
                    "meta-data": "local-hostname: md\n",
                    "network-config": "net-config",
                    "user-data": "user-data",
                    "vendor-data": "vendor-data",
                },
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.custom1",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.meta-data",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/user.network-config",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.user-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.vendor-data",
                ],
            ),
            (  # Assert cloud-init.* config key values preferred over user.*
                False,
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": (
                        '["/1.0/config/user.meta-data",'
                        ' "/1.0/config/user.network-config",'
                        ' "/1.0/config/user.user-data",'
                        ' "/1.0/config/user.vendor-data",'
                        ' "/1.0/config/cloud-init.network-config",'
                        ' "/1.0/config/cloud-init.user-data",'
                        ' "/1.0/config/cloud-init.vendor-data"]'
                    ),
                    "http://lxd/1.0/config/user.meta-data": "user.meta-data",
                    "http://lxd/1.0/config/user.network-config": (
                        "user.network-config"
                    ),
                    "http://lxd/1.0/config/user.user-data": "user.user-data",
                    "http://lxd/1.0/config/user.vendor-data": (
                        "user.vendor-data"
                    ),
                    "http://lxd/1.0/config/cloud-init.meta-data": (
                        "cloud-init.meta-data"
                    ),
                    "http://lxd/1.0/config/cloud-init.network-config": (
                        "cloud-init.network-config"
                    ),
                    "http://lxd/1.0/config/cloud-init.user-data": (
                        "cloud-init.user-data"
                    ),
                    "http://lxd/1.0/config/cloud-init.vendor-data": (
                        "cloud-init.vendor-data"
                    ),
                },
                {
                    "_metadata_api_version": lxd.LXD_SOCKET_API_VERSION,
                    "config": {
                        "user.meta-data": "user.meta-data",
                        "user.network-config": "user.network-config",
                        "user.user-data": "user.user-data",
                        "user.vendor-data": "user.vendor-data",
                        "cloud-init.network-config": (
                            "cloud-init.network-config"
                        ),
                        "cloud-init.user-data": "cloud-init.user-data",
                        "cloud-init.vendor-data": "cloud-init.vendor-data",
                    },
                    "meta-data": "local-hostname: md\n",
                    "network-config": "cloud-init.network-config",
                    "user-data": "cloud-init.user-data",
                    "vendor-data": "cloud-init.vendor-data",
                },
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.meta-data",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/user.network-config",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.user-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config/user.vendor-data",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/cloud-init.network-config",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/cloud-init.user-data",
                    "[GET] [HTTP:200]"
                    " http://lxd/1.0/config/cloud-init.vendor-data",
                    "Ignoring LXD config user.user-data in favor of"
                    " cloud-init.user-data value.",
                    "Ignoring LXD config user.network-config in favor of"
                    " cloud-init.network-config value.",
                    "Ignoring LXD config user.vendor-data in favor of"
                    " cloud-init.vendor-data value.",
                ],
            ),
        ),
    )
    @mock.patch.object(lxd.requests.Session, "get")
    def test_read_metadata_handles_unexpected_content_or_http_status(
        self, m_session_get, get_devices, url_responses, expected, logs, caplog
    ):
        """read_metadata handles valid and invalid content and status codes."""

        def fake_get(url):
            """Mock Response json, ok, status_code, text from url_responses."""
            m_resp = mock.MagicMock()
            content = url_responses.get(url, "")
            m_resp.json.side_effect = lambda: json.loads(content)
            if content:
                mock_ok = mock.PropertyMock(return_value=True)
                mock_status_code = mock.PropertyMock(return_value=200)
            else:
                mock_ok = mock.PropertyMock(return_value=False)
                mock_status_code = mock.PropertyMock(return_value=404)
            type(m_resp).ok = mock_ok
            type(m_resp).status_code = mock_status_code
            mock_content = mock.PropertyMock(
                return_value=content.encode("utf-8")
            )
            type(m_resp).content = mock_content
            return m_resp

        m_session_get.side_effect = fake_get
        metadata_keys = MetaDataKeys.META_DATA | MetaDataKeys.CONFIG
        if get_devices:
            metadata_keys |= MetaDataKeys.DEVICES
        if isinstance(expected, Exception):
            with pytest.raises(type(expected), match=re.escape(str(expected))):
                lxd.read_metadata(metadata_keys=metadata_keys)
        else:
            assert expected == lxd.read_metadata(metadata_keys=metadata_keys)
        for log in logs:
            assert log in caplog.text

    @pytest.mark.parametrize(
        "metadata_keys, expected_get_urls",
        [
            (MetaDataKeys.NONE, []),
            (MetaDataKeys.META_DATA, ["http://lxd/1.0/meta-data"]),
            (MetaDataKeys.CONFIG, ["http://lxd/1.0/config"]),
            (MetaDataKeys.DEVICES, ["http://lxd/1.0/devices"]),
            (
                MetaDataKeys.DEVICES | MetaDataKeys.CONFIG,
                ["http://lxd/1.0/config", "http://lxd/1.0/devices"],
            ),
            (
                MetaDataKeys.ALL,
                [
                    "http://lxd/1.0/meta-data",
                    "http://lxd/1.0/config",
                    "http://lxd/1.0/devices",
                ],
            ),
        ],
    )
    @mock.patch.object(lxd.requests.Session, "get")
    def test_read_metadata_keys(
        self, m_session_get, metadata_keys, expected_get_urls
    ):
        lxd.read_metadata(metadata_keys=metadata_keys)
        assert (
            list(map(mock.call, expected_get_urls))
            == m_session_get.call_args_list
        )

    @mock.patch.object(lxd.requests.Session, "get")
    @mock.patch.object(lxd.time, "sleep")
    def test_socket_retry(self, m_session_get, m_sleep):
        """validate socket retry logic"""

        def generate_return_codes():
            """
            [200]
            [500, 200]
            [500, 500, 200]
            [500, 500, ..., 200]
            """
            five_hundreds = []

            # generate a couple of longer ones to assert timeout condition
            for _ in range(33):
                five_hundreds.append(500)
                yield [*five_hundreds, 200]

        for return_codes in generate_return_codes():
            m = mock.Mock(
                get=mock.Mock(
                    side_effect=[
                        mock.MagicMock(
                            ok=mock.PropertyMock(return_value=True),
                            status_code=code,
                            text=mock.PropertyMock(
                                return_value="properly formatted http response"
                            ),
                        )
                        for code in return_codes
                    ]
                )
            )
            resp = lxd._do_request(m, "http://agua/")

            # assert that 30 iterations or the first 200 code is the final
            # attempt, whichever comes first
            assert min(len(return_codes), 30) == m.get.call_count
            if len(return_codes) < 31:
                assert 200 == resp.status_code
            else:
                assert 500 == resp.status_code
