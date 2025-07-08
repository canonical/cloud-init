# This file is part of cloud-init. See LICENSE file for license information.

import functools
import os
from unittest import mock

import pytest
import responses

from cloudinit import helpers
from cloudinit.sources import DataSourceAliYun as ay
from cloudinit.sources.helpers.aliyun import (
    convert_ecs_metadata_network_config,
)
from cloudinit.util import load_json
from tests.unittests import helpers as test_helpers

DEFAULT_METADATA_RAW = r"""{
  "disks": {
    "bp15spwwhlf8bbbn7xxx": {
      "id": "d-bp15spwwhlf8bbbn7xxx",
      "name": ""
    }
  },
  "dns-conf": {
    "nameservers": [
    "100.100.2.136",
    "100.100.2.138"
    ]
  },
  "hibernation": {
    "configured": "false"
  },
  "instance": {
    "instance-name": "aliyun-test-vm-00",
    "instance-type": "ecs.g8i.large",
    "last-host-landing-time": "2024-11-17 10:02:41",
    "max-netbw-egress": "2560000",
    "max-netbw-ingress": "2560000",
    "virtualization-solution": "ECS Virt",
    "virtualization-solution-version": "2.0"
  },
  "network": {
    "interfaces": {
      "macs": {
        "00:16:3e:14:59:58": {
          "gateway": "172.16.101.253",
          "netmask": "255.255.255.0",
          "network-interface-id": "eni-bp13i3ed90icgdgaxxxx"
        }
      }
    }
  },
  "ntp-conf": {
    "ntp-servers": [
      "ntp1.aliyun.com",
      "ntp1.cloud.aliyuncs.com"
    ]
  },
  "public-keys": {
    "0": {
      "openssh-key": "ssh-rsa AAAAB3Nza"
    },
    "skp-bp1test": {
      "openssh-key": "ssh-rsa AAAAB3Nza"
    }
  },
  "eipv4": "121.66.77.88",
  "hostname": "aliyun-test-vm-00",
  "image-id": "ubuntu_24_04_x64_20G_alibase_20241016.vhd",
  "instance-id": "i-bp15ojxppkmsnyjxxxxx",
  "mac": "00:16:3e:14:59:58",
  "network-type": "vpc",
  "owner-account-id": "123456",
  "private-ipv4": "172.16.111.222",
  "region-id": "cn-hangzhou",
  "serial-number": "3ca05955-a892-46b3-a6fc-xxxxxx",
  "source-address": "http://mirrors.cloud.aliyuncs.com",
  "sub-private-ipv4-list": "172.16.101.215",
  "vpc-cidr-block": "172.16.0.0/12",
  "vpc-id": "vpc-bp1uwvjta7txxxxxxx",
  "vswitch-cidr-block": "172.16.101.0/24",
  "vswitch-id": "vsw-bp12cibmw6078qv123456",
  "zone-id": "cn-hangzhou-j"
}"""

DEFAULT_METADATA = load_json(DEFAULT_METADATA_RAW)

DEFAULT_USERDATA = """\
#cloud-config

hostname: localhost"""

DEFAULT_VENDORDATA = """\
#cloud-config
bootcmd:
- echo hello world > /tmp/vendor"""


class TestAliYunDatasource(test_helpers.CiTestCase):
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
    def default_vendordata(self):
        return DEFAULT_VENDORDATA

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
    def metadata_all_url(self):
        return (
            os.path.join(
                self.metadata_address,
                self.ds.min_metadata_version,
                "meta-data",
            )
            + "/all"
        )

    @property
    def userdata_url(self):
        return os.path.join(
            self.metadata_address, self.ds.min_metadata_version, "user-data"
        )

    @property
    def vendordata_url(self):
        return os.path.join(
            self.metadata_address, self.ds.min_metadata_version, "vendor-data"
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

        register = functools.partial(responses.add, responses.GET)
        register_helper(register, base_url, data)

    def regist_default_server(self, register_json_meta_path=True):
        self.register_mock_metaserver(self.metadata_url, self.default_metadata)
        if register_json_meta_path:
            self.register_mock_metaserver(
                self.metadata_all_url, DEFAULT_METADATA_RAW
            )
        self.register_mock_metaserver(self.userdata_url, self.default_userdata)
        self.register_mock_metaserver(
            self.vendordata_url, self.default_userdata
        )

        self.register_mock_metaserver(self.identity_url, self.default_identity)
        responses.add(responses.PUT, self.token_url, "API-TOKEN")

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

    @responses.activate
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
        self.assertEqual("aliyun", self.ds.platform)
        self.assertEqual(
            "metadata (http://100.100.100.200)", self.ds.subplatform
        )

    @responses.activate
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_with_mock_server_without_json_path(self, m_is_aliyun, m_resolv):
        m_is_aliyun.return_value = True
        self.regist_default_server(register_json_meta_path=False)
        ret = self.ds.get_data()
        self.assertEqual(True, ret)
        self.assertEqual(1, m_is_aliyun.call_count)
        self._test_get_data()
        self._test_get_sshkey()
        self._test_get_iid()
        self._test_host_name()
        self.assertEqual("aliyun", self.ds.cloud_name)
        self.assertEqual("aliyun", self.ds.platform)
        self.assertEqual(
            "metadata (http://100.100.100.200)", self.ds.subplatform
        )

    @responses.activate
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv6Network")
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_FreeBSD")
    @pytest.mark.usefixtures("disable_netdev_info")
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
        self.assertEqual("aliyun", self.ds.platform)
        self.assertEqual(
            "metadata (http://100.100.100.200)", self.ds.subplatform
        )

    @responses.activate
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

    def test_route_metric_calculated_with_multiple_network_cards(self):
        """Test that route-metric code works with multiple network cards"""
        netcfg = convert_ecs_metadata_network_config(
            {
                "interfaces": {
                    "macs": {
                        "00:16:3e:14:59:58": {
                            "ipv6-gateway": "2408:xxxxx",
                            "ipv6s": "[2408:xxxxxx]",
                            "network-interface-id": "eni-bp13i1xxxxx",
                        },
                        "00:16:3e:39:43:27": {
                            "gateway": "172.16.101.253",
                            "netmask": "255.255.255.0",
                            "network-interface-id": "eni-bp13i2xxxx",
                        },
                    }
                }
            },
            macs_to_nics={
                "00:16:3e:14:59:58": "eth0",
                "00:16:3e:39:43:27": "eth1",
            },
        )

        met0 = netcfg["ethernets"]["eth0"]["dhcp4-overrides"]["route-metric"]
        met1 = netcfg["ethernets"]["eth1"]["dhcp4-overrides"]["route-metric"]

        # route-metric numbers should be 100 apart
        assert 100 == abs(met0 - met1)

        # No policy routing
        assert not {"routing-policy", "routes"}.intersection(
            netcfg["ethernets"]["eth0"].keys()
        )
        assert not {"routing-policy", "routes"}.intersection(
            netcfg["ethernets"]["eth1"].keys()
        )

        # eth0 network meta-data  have ipv6s info, ipv6 should True
        met0_dhcp6 = netcfg["ethernets"]["eth0"]["dhcp6"]
        assert met0_dhcp6 is True

        netcfg = convert_ecs_metadata_network_config(
            {
                "interfaces": {
                    "macs": {
                        "00:16:3e:14:59:58": {
                            "gateway": "172.16.101.253",
                            "netmask": "255.255.255.0",
                            "network-interface-id": "eni-bp13ixxxx",
                        }
                    }
                }
            },
            macs_to_nics={"00:16:3e:14:59:58": "eth0"},
        )
        met0 = netcfg["ethernets"]["eth0"]
        # single network card would have no dhcp4-overrides
        assert "dhcp4-overrides" not in met0


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
