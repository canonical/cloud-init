# This file is part of cloud-init. See LICENSE file for license information.

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

DS_PATH = "cloudinit.sources.DataSourceLXD."


LStatResponse = namedtuple("lstatresponse", "st_mode")


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
    network_cfg = deepcopy(NETWORK_V1)
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


@pytest.fixture
def lxd_metadata():
    return LXD_V1_METADATA


@pytest.fixture
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
    def test_net_v2_based_on_network_mode_virt_type_and_uname_machine(
        self,
        m_which,
        m_subp,
        m_system_info,
        uname_machine,
        systemd_detect_virt,
        expected,
    ):
        """Return network config v2 based on uname -m, systemd-detect-virt."""
        if systemd_detect_virt is None:
            m_which.return_value = None
        m_system_info.return_value = {"uname": ["", "", "", "", uname_machine]}
        m_subp.return_value = (systemd_detect_virt, "")
        assert expected == lxd.generate_fallback_network_config()
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
        "url_responses,expected,logs",
        (
            (  # Assert non-JSON format from config route
                {
                    "http://lxd/1.0/meta-data": "local-hostname: md\n",
                    "http://lxd/1.0/config": "[NOT_JSON",
                },
                InvalidMetaDataException(
                    "Unable to determine cloud-init config from"
                    " http://lxd/1.0/config. Expected JSON but found:"
                    " [NOT_JSON"
                ),
                [
                    "[GET] [HTTP:200] http://lxd/1.0/meta-data",
                    "[GET] [HTTP:200] http://lxd/1.0/config",
                ],
            ),
            (  # Assert success on just meta-data
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
            (  # Assert 404s for config routes log skipping
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
            (  # Assert cloud-init.* config key values prefered over user.*
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
        self, session_get, url_responses, expected, logs, caplog
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
            mock_text = mock.PropertyMock(return_value=content)
            type(m_resp).text = mock_text
            return m_resp

        session_get.side_effect = fake_get

        if isinstance(expected, Exception):
            with pytest.raises(type(expected), match=re.escape(str(expected))):
                lxd.read_metadata()
        else:
            assert expected == lxd.read_metadata()
        caplogs = caplog.text
        for log in logs:
            assert log in caplogs


# vi: ts=4 expandtab
