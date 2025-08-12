# This file is part of cloud-init. See LICENSE file for license information.

import functools
import os
from unittest import mock

import pytest
import responses

from cloudinit.sources import DataSourceAliYun as ay
from cloudinit.sources.helpers.aliyun import (
    convert_ecs_metadata_network_config,
)
from cloudinit.util import load_json

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


@pytest.fixture
def ds(paths):
    cfg = {"datasource": {"AliYun": {"timeout": "1", "max_wait": "1"}}}
    distro = {}
    return ay.DataSourceAliYun(cfg, distro, paths)


@pytest.fixture
def metadata_address(ds):
    return ds.metadata_urls[0]


def register_mock_metaserver(base_url, data):
    def register_helper(register, base_url, body):
        if isinstance(body, str):
            register(base_url, body)
        elif isinstance(body, list):
            register(base_url.rstrip("/"), "\n".join(body) + "\n")
        elif isinstance(body, dict):
            if not body:
                register(base_url.rstrip("/") + "/", "not found", status=404)
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


@pytest.fixture
def regist_default_server(ds, metadata_address):
    metadata_url = (
        os.path.join(
            metadata_address,
            ds.min_metadata_version,
            "meta-data",
        )
        + "/"
    )
    register_mock_metaserver(metadata_url, DEFAULT_METADATA)

    userdata_url = os.path.join(
        metadata_address, ds.min_metadata_version, "user-data"
    )
    register_mock_metaserver(userdata_url, DEFAULT_USERDATA)

    vendordata_url = os.path.join(
        metadata_address, ds.min_metadata_version, "vendor-data"
    )
    register_mock_metaserver(vendordata_url, DEFAULT_USERDATA)

    # EC2 provides an instance-identity document which must return 404 here
    # for this test to pass.
    default_identity = {}
    identity_url = os.path.join(
        metadata_address,
        ds.min_metadata_version,
        "dynamic",
        "instance-identity",
    )
    register_mock_metaserver(identity_url, default_identity)

    token_url = os.path.join(metadata_address, "latest", "api", "token")
    responses.add(responses.PUT, token_url, "API-TOKEN")


@pytest.fixture
def regist_json_meta_path(ds, metadata_address):
    metadata_all_url = (
        os.path.join(
            metadata_address,
            ds.min_metadata_version,
            "meta-data",
        )
        + "/all"
    )
    register_mock_metaserver(metadata_all_url, DEFAULT_METADATA_RAW)


class TestAliYunDatasource:

    def _test_get_data(self, ds):
        assert ds.metadata == DEFAULT_METADATA
        assert ds.userdata_raw == DEFAULT_USERDATA.encode("utf8")

    def _test_get_sshkey(self, ds):
        pub_keys = [
            v["openssh-key"]
            for (_, v) in DEFAULT_METADATA["public-keys"].items()
        ]
        assert ds.get_public_ssh_keys() == pub_keys

    def _test_get_iid(self, ds):
        assert DEFAULT_METADATA["instance-id"] == ds.get_instance_id()

    def _test_host_name(self, ds):
        assert DEFAULT_METADATA["hostname"] == ds.get_hostname().hostname

    @responses.activate
    @pytest.mark.usefixtures("regist_default_server", "regist_json_meta_path")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_with_mock_server(self, m_is_aliyun, m_resolv, ds):
        m_is_aliyun.return_value = True
        ret = ds.get_data()
        assert True is ret
        assert 1 == m_is_aliyun.call_count
        self._test_get_data(ds)
        self._test_get_sshkey(ds)
        self._test_get_iid(ds)
        self._test_host_name(ds)
        assert "aliyun" == ds.cloud_name
        assert "aliyun" == ds.platform
        assert "metadata (http://100.100.100.200)" == ds.subplatform

    @responses.activate
    @pytest.mark.usefixtures("regist_default_server")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_with_mock_server_without_json_path(
        self, m_is_aliyun, m_resolv, ds
    ):
        m_is_aliyun.return_value = True
        ret = ds.get_data()
        assert True is ret
        assert 1 == m_is_aliyun.call_count
        self._test_get_data(ds)
        self._test_get_sshkey(ds)
        self._test_get_iid(ds)
        self._test_host_name(ds)
        assert "aliyun" == ds.cloud_name
        assert "aliyun" == ds.platform
        assert "metadata (http://100.100.100.200)" == ds.subplatform

    @responses.activate
    @pytest.mark.usefixtures("regist_default_server", "regist_json_meta_path")
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
        ds,
        paths,
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
        ds = ay.DataSourceAliYunLocal(cfg, distro, paths)
        ret = ds.get_data()
        assert True is ret
        assert 1 == m_is_aliyun.call_count
        self._test_get_data(ds)
        self._test_get_sshkey(ds)
        self._test_get_iid(ds)
        self._test_host_name(ds)
        assert "aliyun" == ds.cloud_name
        assert "aliyun" == ds.platform
        assert "metadata (http://100.100.100.200)" == ds.subplatform

    @responses.activate
    @pytest.mark.usefixtures("regist_default_server", "regist_json_meta_path")
    @mock.patch("cloudinit.sources.DataSourceAliYun._is_aliyun")
    def test_returns_false_when_not_on_aliyun(self, m_is_aliyun, ds):
        """If is_aliyun returns false, then get_data should return False."""
        m_is_aliyun.return_value = False
        ret = ds.get_data()
        assert 1 == m_is_aliyun.call_count
        assert False is ret

    def test_parse_public_keys(self):
        public_keys = {}
        assert ay.parse_public_keys(public_keys) == []

        public_keys = {"key-pair-0": "ssh-key-0"}
        assert ay.parse_public_keys(public_keys) == [public_keys["key-pair-0"]]

        public_keys = {"key-pair-0": "ssh-key-0", "key-pair-1": "ssh-key-1"}
        assert set(ay.parse_public_keys(public_keys)) == set(
            [public_keys["key-pair-0"], public_keys["key-pair-1"]]
        )

        public_keys = {"key-pair-0": ["ssh-key-0", "ssh-key-1"]}
        assert ay.parse_public_keys(public_keys) == public_keys["key-pair-0"]

        public_keys = {"key-pair-0": {"openssh-key": []}}
        assert ay.parse_public_keys(public_keys) == []

        public_keys = {"key-pair-0": {"openssh-key": "ssh-key-0"}}
        assert ay.parse_public_keys(public_keys) == [
            public_keys["key-pair-0"]["openssh-key"]
        ]

        public_keys = {
            "key-pair-0": {"openssh-key": ["ssh-key-0", "ssh-key-1"]}
        }
        assert (
            ay.parse_public_keys(public_keys)
            == public_keys["key-pair-0"]["openssh-key"]
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


class TestIsAliYun:
    ALIYUN_PRODUCT = "Alibaba Cloud ECS"
    read_dmi_data_expected = [mock.call("system-product-name")]

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_true_on_aliyun_product(self, m_read_dmi_data):
        """Should return true if the dmi product data has expected value."""
        m_read_dmi_data.return_value = self.ALIYUN_PRODUCT
        ret = ay._is_aliyun()
        assert self.read_dmi_data_expected == m_read_dmi_data.call_args_list
        assert True is ret

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_false_on_empty_string(self, m_read_dmi_data):
        """Should return false on empty value returned."""
        m_read_dmi_data.return_value = ""
        ret = ay._is_aliyun()
        assert self.read_dmi_data_expected == m_read_dmi_data.call_args_list
        assert False is ret

    @mock.patch("cloudinit.sources.DataSourceAliYun.dmi.read_dmi_data")
    def test_false_on_unknown_string(self, m_read_dmi_data):
        """Should return false on an unrelated string."""
        m_read_dmi_data.return_value = "cubs win"
        ret = ay._is_aliyun()
        assert self.read_dmi_data_expected == m_read_dmi_data.call_args_list
        assert False is ret
