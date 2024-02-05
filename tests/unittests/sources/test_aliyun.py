# This file is part of cloud-init. See LICENSE file for license information.

import functools
import os
from unittest import mock

import responses

from cloudinit import helpers
from cloudinit.sources import DataSourceAliYun as ay
from cloudinit.sources.DataSourceEc2 import convert_ec2_metadata_network_config
from tests.unittests import helpers as test_helpers

DEFAULT_METADATA = {
    "instance-id": "aliyun-test-vm-00",
    "eipv4": "10.0.0.1",
    "hostname": "test-hostname",
    "image-id": "m-test",
    "launch-index": "0",
    "mac": "00:16:3e:00:00:00",
    "network-type": "vpc",
    "private-ipv4": "192.168.0.1",
    "serial-number": "test-string",
    "vpc-cidr-block": "192.168.0.0/16",
    "vpc-id": "test-vpc",
    "vswitch-id": "test-vpc",
    "vswitch-cidr-block": "192.168.0.0/16",
    "zone-id": "test-zone-1",
    "ntp-conf": {
        "ntp_servers": [
            "ntp1.aliyun.com",
            "ntp2.aliyun.com",
            "ntp3.aliyun.com",
        ]
    },
    "source-address": [
        "http://mirrors.aliyun.com",
        "http://mirrors.aliyuncs.com",
    ],
    "public-keys": {
        "key-pair-1": {"openssh-key": "ssh-rsa AAAAB3..."},
        "key-pair-2": {"openssh-key": "ssh-rsa AAAAB3..."},
    },
}

DEFAULT_USERDATA = """\
#cloud-config

hostname: localhost"""


class TestAliYunDatasource(test_helpers.ResponsesTestCase):
    def setUp(self):
        super(TestAliYunDatasource, self).setUp()
        cfg = {"datasource": {"AliYun": {"timeout": "1", "max_wait": "1"}}}
        distro = {}
        paths = helpers.Paths({"run_dir": self.tmp_dir()})
        self.ds = ay.DataSourceAliYun(cfg, distro, paths)
        self.metadata_address = self.ds.metadata_urls[0]

    @property
    def default_metadata(self):
        return DEFAULT_METADATA

    @property
    def default_userdata(self):
        return DEFAULT_USERDATA

    @property
    def metadata_url(self):
        return (
            os.path.join(
                self.metadata_address,
                self.ds.min_metadata_version,
                "meta-data",
            )
            + "/"
        )

    @property
    def userdata_url(self):
        return os.path.join(
            self.metadata_address, self.ds.min_metadata_version, "user-data"
        )

    # EC2 provides an instance-identity document which must return 404 here
    # for this test to pass.
    @property
    def default_identity(self):
        return {}

    @property
    def identity_url(self):
        return os.path.join(
            self.metadata_address,
            self.ds.min_metadata_version,
            "dynamic",
            "instance-identity",
        )

    @property
    def token_url(self):
        return os.path.join(
            self.metadata_address,
            "latest",
            "api",
            "token",
        )

    def register_mock_metaserver(self, base_url, data):
        def register_helper(register, base_url, body):
            if isinstance(body, str):
                register(base_url, body)
            elif isinstance(body, list):
                register(base_url.rstrip("/"), "\n".join(body) + "\n")
            elif isinstance(body, dict):
                if not body:
                    register(
                        base_url.rstrip("/") + "/", "not found", status=404
                    )
                vals = []
                for k, v in body.items():
                    if isinstance(v, (str, list)):
                        suffix = k.rstrip("/")
                    else:
                        suffix = k.rstrip("/") + "/"
                    vals.append(suffix)
                    url = base_url.rstrip("/") + "/" + suffix
                    register_helper(register, url, v)
                register(base_url, "\n".join(vals) + "\n")

        register = functools.partial(self.responses.add, responses.GET)
        register_helper(register, base_url, data)

    def regist_default_server(self):
        self.register_mock_metaserver(self.metadata_url, self.default_metadata)
        self.register_mock_metaserver(self.userdata_url, self.default_userdata)
        self.register_mock_metaserver(self.identity_url, self.default_identity)
        self.responses.add(responses.PUT, self.token_url, "API-TOKEN")

    def _test_get_data(self):
        self.assertEqual(self.ds.metadata, self.default_metadata)
        self.assertEqual(
            self.ds.userdata_raw, self.default_userdata.encode("utf8")
        )

    def _test_get_sshkey(self):
        pub_keys = [
            v["openssh-key"]
            for (_, v) in self.default_metadata["public-keys"].items()
        ]
        self.assertEqual(self.ds.get_public_ssh_keys(), pub_keys)

    def _test_get_iid(self):
        self.assertEqual(
            self.default_metadata["instance-id"], self.ds.get_instance_id()
        )

    def _test_host_name(self):
        self.assertEqual(
            self.default_metadata["hostname"], self.ds.get_hostname().hostname
        )

    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_with_mock_server(self, m_is_aliyun, m_resolv):
        m_is_aliyun.return_value = True
        self.regist_default_server()
        ret = self.ds.get_data()
        self.assertEqual(True, ret)
        self.assertEqual(1, m_is_aliyun.call_count)
        self._test_get_data()
        self._test_get_sshkey()
        self._test_get_iid()
        self._test_host_name()
        self.assertEqual("aliyun", self.ds.cloud_name)
        self.assertEqual("ec2", self.ds.platform)
        self.assertEqual(
            "metadata (http://100.100.100.200)", self.ds.subplatform
        )

    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv6Network")
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_FreeBSD")
    def test_aliyun_local_with_mock_server(
        self,
        m_is_bsd,
        m_dhcp,
        m_fallback_nic,
        m_is_aliyun,
        m_resolva,
        m_net4,
        m_net6,
    ):
        m_is_aliyun.return_value = True
        m_fallback_nic.return_value = "eth9"
        m_dhcp.return_value = {
            "interface": "eth9",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
            "broadcast-address": "192.168.2.255",
        }
        m_is_bsd.return_value = False
        cfg = {"datasource": {"AliYun": {"timeout": "1", "max_wait": "1"}}}
        distro = mock.MagicMock()
        paths = helpers.Paths({"run_dir": self.tmp_dir()})
        self.ds = ay.DataSourceAliYunLocal(cfg, distro, paths)
        self.regist_default_server()
        ret = self.ds.get_data()
        self.assertEqual(True, ret)
        self.assertEqual(1, m_is_aliyun.call_count)
        self._test_get_data()
        self._test_get_sshkey()
        self._test_get_iid()
        self._test_host_name()
        self.assertEqual("aliyun", self.ds.cloud_name)
        self.assertEqual("ec2", self.ds.platform)
        self.assertEqual(
            "metadata (http://100.100.100.200)", self.ds.subplatform
        )

    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_returns_false_when_not_on_aliyun(self, m_is_aliyun):
        """If is_aliyun returns false, then get_data should return False."""
        m_is_aliyun.return_value = False
        self.regist_default_server()
        ret = self.ds.get_data()
        self.assertEqual(1, m_is_aliyun.call_count)
        self.assertEqual(False, ret)

    def test_parse_public_keys(self):
        public_keys = {}
        self.assertEqual(ay.parse_public_keys(public_keys), [])

        public_keys = {"key-pair-0": "ssh-key-0"}
        self.assertEqual(
            ay.parse_public_keys(public_keys), [public_keys["key-pair-0"]]
        )

        public_keys = {"key-pair-0": "ssh-key-0", "key-pair-1": "ssh-key-1"}
        self.assertEqual(
            set(ay.parse_public_keys(public_keys)),
            set([public_keys["key-pair-0"], public_keys["key-pair-1"]]),
        )

        public_keys = {"key-pair-0": ["ssh-key-0", "ssh-key-1"]}
        self.assertEqual(
            ay.parse_public_keys(public_keys), public_keys["key-pair-0"]
        )

        public_keys = {"key-pair-0": {"openssh-key": []}}
        self.assertEqual(ay.parse_public_keys(public_keys), [])

        public_keys = {"key-pair-0": {"openssh-key": "ssh-key-0"}}
        self.assertEqual(
            ay.parse_public_keys(public_keys),
            [public_keys["key-pair-0"]["openssh-key"]],
        )

        public_keys = {
            "key-pair-0": {"openssh-key": ["ssh-key-0", "ssh-key-1"]}
        }
        self.assertEqual(
            ay.parse_public_keys(public_keys),
            public_keys["key-pair-0"]["openssh-key"],
        )

    def test_route_metric_calculated_without_device_number(self):
        """Test that route-metric code works without `device-number`

        `device-number` is part of EC2 metadata, but not supported on aliyun.
        Attempting to access it will raise a KeyError.

        LP: #1917875
        """
        netcfg = convert_ec2_metadata_network_config(
            {
                "interfaces": {
                    "macs": {
                        "06:17:04:d7:26:09": {
                            "interface-id": "eni-e44ef49e",
                        },
                        "06:17:04:d7:26:08": {
                            "interface-id": "eni-e44ef49f",
                        },
                    }
                }
            },
            macs_to_nics={
                "06:17:04:d7:26:09": "eth0",
                "06:17:04:d7:26:08": "eth1",
            },
        )

        met0 = netcfg["ethernets"]["eth0"]["dhcp4-overrides"]["route-metric"]
        met1 = netcfg["ethernets"]["eth1"]["dhcp4-overrides"]["route-metric"]

        # route-metric numbers should be 100 apart
        assert 100 == abs(met0 - met1)


class TestIsAliYun(test_helpers.CiTestCase):
    ALIYUN_PRODUCT = "Alibaba Cloud ECS"
    read_dmi_data_expected = [mock.call("system-product-name")]

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_true_on_aliyun_product(self, m_read_dmi_data):
        """Should return true if the dmi product data has expected value."""
        m_read_dmi_data.return_value = self.ALIYUN_PRODUCT
        ret = ay._is_aliyun()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(True, ret)

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_false_on_empty_string(self, m_read_dmi_data):
        """Should return false on empty value returned."""
        m_read_dmi_data.return_value = ""
        ret = ay._is_aliyun()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(False, ret)

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_false_on_unknown_string(self, m_read_dmi_data):
        """Should return false on an unrelated string."""
        m_read_dmi_data.return_value = "cubs win"
        ret = ay._is_aliyun()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(False, ret)
