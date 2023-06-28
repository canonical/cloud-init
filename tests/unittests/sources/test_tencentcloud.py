import functools
import os
from unittest import mock

import responses

from cloudinit import helpers
from cloudinit.sources import DataSourceTencentCloud as TencentCloud
from cloudinit.sources.DataSourceEc2 import convert_ec2_metadata_network_config
from tests.unittests import helpers as test_helpers

DEFAULT_METADATA = {
    "instance-id": "tencentcloud-test-vm-00",
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
            "ntp1.tencent.com",
            "ntp2.tencent.com",
            "ntp3.tencent.com",
        ]
    },
    "source-address": [
        "https://cloud.tencent.com/",
    ],
    "public-keys": {
        "key-pair-1": {"user": "root", "openssh-key": "ssh-rsa AAAAB3..."},
        "key-pair-2": {"user": "root", "openssh-key": "ssh-rsa AAAAB3..."},
    },
}

DEFAULT_USERDATA = """\
#cloud-config

hostname: localhost"""


class TestTencentCloudDatasource(test_helpers.ResponsesTestCase):
    def setUp(self):
        super(TestTencentCloudDatasource, self).setUp()
        cfg = {
            "datasource": {"TencentCloud": {"timeout": "1", "max_wait": "1"}}
        }
        distro = {}
        paths = helpers.Paths({"run_dir": self.tmp_dir()})
        self.ds = TencentCloud.DataSourceTencentCloud(cfg, distro, paths)
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

    def register_default_server(self):
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

    def test_parse_public_keys(self):
        public_keys = {}
        self.assertEqual(TencentCloud.parse_public_keys(public_keys), [])

        public_keys = {"key-pair-0": "ssh-key-0"}
        self.assertEqual(
            TencentCloud.parse_public_keys(public_keys),
            [public_keys["key-pair-0"]],
        )

        public_keys = {"key-pair-0": "ssh-key-0", "key-pair-1": "ssh-key-1"}
        self.assertEqual(
            set(TencentCloud.parse_public_keys(public_keys)),
            set([public_keys["key-pair-0"], public_keys["key-pair-1"]]),
        )

        public_keys = {"key-pair-0": ["ssh-key-0", "ssh-key-1"]}
        self.assertEqual(
            TencentCloud.parse_public_keys(public_keys),
            public_keys["key-pair-0"],
        )

        public_keys = {"key-pair-0": {"openssh-key": []}}
        self.assertEqual(TencentCloud.parse_public_keys(public_keys), [])

        public_keys = {"key-pair-0": {"openssh-key": "ssh-key-0"}}
        self.assertEqual(
            TencentCloud.parse_public_keys(public_keys),
            [public_keys["key-pair-0"]["openssh-key"]],
        )

        public_keys = {
            "key-pair-0": {"openssh-key": ["ssh-key-0", "ssh-key-1"]}
        }
        self.assertEqual(
            TencentCloud.parse_public_keys(public_keys),
            public_keys["key-pair-0"]["openssh-key"],
        )

    def test_route_metric_calculated_without_device_number(self):
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


class TestIsTencentCloud(test_helpers.CiTestCase):
    TENCENTCLOUD_PRODUCT = "Tencent Cloud CVM"
    read_dmi_data_expected = [mock.call("system-product-name")]

    @mock.patch("cloudinit.sources.DataSourceTencentCloud.dmi.read_dmi_data")
    def test_true_on_tencentcloud_product(self, m_read_dmi_data):
        """Should return true if the dmi product data has expected value."""
        m_read_dmi_data.return_value = self.TENCENTCLOUD_PRODUCT
        ret = TencentCloud._is_tencentcloud()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(True, ret)

    @mock.patch("cloudinit.sources.DataSourceTencentCloud.dmi.read_dmi_data")
    def test_false_on_empty_string(self, m_read_dmi_data):
        """Should return false on empty value returned."""
        m_read_dmi_data.return_value = ""
        ret = TencentCloud._is_tencentcloud()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(False, ret)

    @mock.patch("cloudinit.sources.DataSourceTencentCloud.dmi.read_dmi_data")
    def test_false_on_unknown_string(self, m_read_dmi_data):
        """Should return false on an unrelated string."""
        m_read_dmi_data.return_value = "cubs win"
        ret = TencentCloud._is_tencentcloud()
        self.assertEqual(
            self.read_dmi_data_expected, m_read_dmi_data.call_args_list
        )
        self.assertEqual(False, ret)
