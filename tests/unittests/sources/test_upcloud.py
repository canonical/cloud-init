# Author: Antti Myyrä <antti.myyra@upcloud.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json

from cloudinit import helpers, importer, settings, sources
from cloudinit.sources.DataSourceUpCloud import (
    DataSourceUpCloud,
    DataSourceUpCloudLocal,
)
from tests.unittests.helpers import CiTestCase, mock

UC_METADATA = json.loads(
    """
{
  "cloud_name": "upcloud",
  "instance_id": "00322b68-0096-4042-9406-faad61922128",
  "hostname": "test.example.com",
  "platform": "servers",
  "subplatform": "metadata (http://169.254.169.254)",
  "public_keys": [
    "ssh-rsa AAAAB.... test1@example.com",
    "ssh-rsa AAAAB.... test2@example.com"
  ],
  "region": "fi-hel2",
  "network": {
    "interfaces": [
      {
        "index": 1,
        "ip_addresses": [
          {
            "address": "94.237.105.53",
            "dhcp": true,
            "dns": [
              "94.237.127.9",
              "94.237.40.9"
            ],
            "family": "IPv4",
            "floating": false,
            "gateway": "94.237.104.1",
            "network": "94.237.104.0/22"
          },
          {
            "address": "94.237.105.50",
            "dhcp": false,
            "dns": null,
            "family": "IPv4",
            "floating": true,
            "gateway": "",
            "network": "94.237.105.50/32"
          }
        ],
        "mac": "3a:d6:ba:4a:36:e7",
        "network_id": "031457f4-0f8c-483c-96f2-eccede02909c",
        "type": "public"
      },
      {
        "index": 2,
        "ip_addresses": [
          {
            "address": "10.6.3.27",
            "dhcp": true,
            "dns": null,
            "family": "IPv4",
            "floating": false,
            "gateway": "10.6.0.1",
            "network": "10.6.0.0/22"
          }
        ],
        "mac": "3a:d6:ba:4a:84:cc",
        "network_id": "03d82553-5bea-4132-b29a-e1cf67ec2dd1",
        "type": "utility"
      },
      {
        "index": 3,
        "ip_addresses": [
          {
            "address": "2a04:3545:1000:720:38d6:baff:fe4a:63e7",
            "dhcp": true,
            "dns": [
              "2a04:3540:53::1",
              "2a04:3544:53::1"
            ],
            "family": "IPv6",
            "floating": false,
            "gateway": "2a04:3545:1000:720::1",
            "network": "2a04:3545:1000:720::/64"
          }
        ],
        "mac": "3a:d6:ba:4a:63:e7",
        "network_id": "03000000-0000-4000-8046-000000000000",
        "type": "public"
      },
      {
        "index": 4,
        "ip_addresses": [
          {
            "address": "172.30.1.10",
            "dhcp": true,
            "dns": null,
            "family": "IPv4",
            "floating": false,
            "gateway": "172.30.1.1",
            "network": "172.30.1.0/24"
          }
        ],
        "mac": "3a:d6:ba:4a:8a:e1",
        "network_id": "035a0a4a-7704-4de5-820d-189fc8132714",
        "type": "private"
      }
    ],
    "dns": [
      "94.237.127.9",
      "94.237.40.9"
    ]
  },
  "storage": {
    "disks": [
      {
        "id": "014efb65-223b-4d44-8f0a-c29535b88dcf",
        "serial": "014efb65223b4d448f0a",
        "size": 10240,
        "type": "disk",
        "tier": "maxiops"
      }
    ]
  },
  "tags": [],
  "user_data": "",
  "vendor_data": ""
}
"""
)

UC_METADATA[
    "user_data"
] = b"""#cloud-config
runcmd:
- [touch, /root/cloud-init-worked ]
"""

MD_URL = "http://169.254.169.254/metadata/v1.json"


def _mock_dmi():
    return True, "00322b68-0096-4042-9406-faad61922128"


class TestUpCloudMetadata(CiTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        super(TestUpCloudMetadata, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self, get_sysinfo=_mock_dmi):
        ds = DataSourceUpCloud(
            settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": self.tmp})
        )
        if get_sysinfo:
            ds._get_sysinfo = get_sysinfo
        return ds

    @mock.patch("cloudinit.sources.helpers.upcloud.read_sysinfo")
    def test_returns_false_not_on_upcloud(self, m_read_sysinfo):
        m_read_sysinfo.return_value = (False, None)
        ds = self.get_ds(get_sysinfo=None)
        self.assertEqual(False, ds.get_data())
        self.assertTrue(m_read_sysinfo.called)

    @mock.patch("cloudinit.sources.helpers.upcloud.read_metadata")
    def test_metadata(self, mock_readmd):
        mock_readmd.return_value = UC_METADATA.copy()

        ds = self.get_ds()
        ds.perform_dhcp_setup = False

        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(mock_readmd.called)

        self.assertEqual(UC_METADATA.get("user_data"), ds.get_userdata_raw())
        self.assertEqual(
            UC_METADATA.get("vendor_data"), ds.get_vendordata_raw()
        )
        self.assertEqual(UC_METADATA.get("region"), ds.availability_zone)
        self.assertEqual(UC_METADATA.get("instance_id"), ds.get_instance_id())
        self.assertEqual(UC_METADATA.get("cloud_name"), ds.cloud_name)

        self.assertEqual(
            UC_METADATA.get("public_keys"), ds.get_public_ssh_keys()
        )
        self.assertIsInstance(ds.get_public_ssh_keys(), list)


class TestUpCloudNetworkSetup(CiTestCase):
    """
    Test reading the meta-data on networked context
    """

    def setUp(self):
        super(TestUpCloudNetworkSetup, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self, get_sysinfo=_mock_dmi):
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        ds = DataSourceUpCloudLocal(
            settings.CFG_BUILTIN, distro, helpers.Paths({"run_dir": self.tmp})
        )
        if get_sysinfo:
            ds._get_sysinfo = get_sysinfo
        return ds

    @mock.patch("cloudinit.sources.helpers.upcloud.read_metadata")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    def test_network_configured_metadata(
        self, m_net, m_dhcp, m_fallback_nic, mock_readmd
    ):
        mock_readmd.return_value = UC_METADATA.copy()

        m_fallback_nic.return_value = "eth1"
        m_dhcp.return_value = {
            "interface": "eth1",
            "fixed-address": "10.6.3.27",
            "routers": "10.6.0.1",
            "subnet-mask": "22",
            "broadcast-address": "10.6.3.255",
        }

        ds = self.get_ds()

        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(m_dhcp.called)
        m_dhcp.assert_called_with(ds.distro, "eth1", None)

        m_net.assert_called_once_with(
            ds.distro,
            broadcast="10.6.3.255",
            interface="eth1",
            ip="10.6.3.27",
            prefix_or_mask="22",
            router="10.6.0.1",
            static_routes=None,
        )

        self.assertTrue(mock_readmd.called)

        self.assertEqual(UC_METADATA.get("region"), ds.availability_zone)
        self.assertEqual(UC_METADATA.get("instance_id"), ds.get_instance_id())
        self.assertEqual(UC_METADATA.get("cloud_name"), ds.cloud_name)

    @mock.patch("cloudinit.sources.helpers.upcloud.read_metadata")
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_network_configuration(self, m_get_by_mac, mock_readmd):
        mock_readmd.return_value = UC_METADATA.copy()

        raw_ifaces = UC_METADATA.get("network").get("interfaces")
        self.assertEqual(4, len(raw_ifaces))

        m_get_by_mac.return_value = {
            raw_ifaces[0].get("mac"): "eth0",
            raw_ifaces[1].get("mac"): "eth1",
            raw_ifaces[2].get("mac"): "eth2",
            raw_ifaces[3].get("mac"): "eth3",
        }

        ds = self.get_ds()
        ds.perform_dhcp_setup = False

        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(mock_readmd.called)

        netcfg = ds.network_config

        self.assertEqual(1, netcfg.get("version"))

        config = netcfg.get("config")
        self.assertIsInstance(config, list)
        self.assertEqual(5, len(config))
        self.assertEqual("physical", config[3].get("type"))

        self.assertEqual(
            raw_ifaces[2].get("mac"), config[2].get("mac_address")
        )
        self.assertEqual(1, len(config[2].get("subnets")))
        self.assertEqual(
            "ipv6_dhcpv6-stateless", config[2].get("subnets")[0].get("type")
        )

        self.assertEqual(2, len(config[0].get("subnets")))
        self.assertEqual("static", config[0].get("subnets")[1].get("type"))

        dns = config[4]
        self.assertEqual("nameserver", dns.get("type"))
        self.assertEqual(2, len(dns.get("address")))
        self.assertEqual(
            UC_METADATA.get("network").get("dns")[1], dns.get("address")[1]
        )


class TestUpCloudDatasourceLoading(CiTestCase):
    def test_get_datasource_list_returns_in_local(self):
        deps = (sources.DEP_FILESYSTEM,)
        ds_list = sources.DataSourceUpCloud.get_datasource_list(deps)
        self.assertEqual(ds_list, [DataSourceUpCloudLocal])

    def test_get_datasource_list_returns_in_normal(self):
        deps = (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)
        ds_list = sources.DataSourceUpCloud.get_datasource_list(deps)
        self.assertEqual(ds_list, [DataSourceUpCloud])

    @mock.patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    def test_list_sources_finds_ds(self):
        found = sources.list_sources(
            ["UpCloud"],
            (sources.DEP_FILESYSTEM, sources.DEP_NETWORK),
            ["cloudinit.sources"],
        )
        self.assertEqual([DataSourceUpCloud], found)
