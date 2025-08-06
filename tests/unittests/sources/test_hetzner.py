# Copyright (C) 2018 Jonas Keidel
#
# Author: Jonas Keidel <jonas.keidel@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import pytest

from cloudinit import settings, util
from cloudinit.sources import DataSourceHetzner
from tests.unittests.helpers import mock

METADATA = util.load_yaml(
    """
hostname: cloudinit-test
instance-id: 123456
local-ipv4: ''
network-config:
  config:
  - mac_address: 96:00:00:08:19:da
    name: eth0
    subnets:
    - dns_nameservers:
      - 185.12.64.1
      - 185.12.64.2
      ipv4: true
      type: dhcp
    - address: 2a01:4f8:beef:beef::1/64
      dns_nameservers:
      - 2a01:4ff:ff00::add:2
      - 2a01:4ff:ff00::add:1
      gateway: fe80::1
      ipv6: true
    type: physical
  version: 1
network-sysconfig: "DEVICE='eth0'\nTYPE=Ethernet\nBOOTPROTO=dhcp\n\
  ONBOOT='yes'\nHWADDR=96:00:00:08:19:da\n\
  IPV6INIT=yes\nIPV6ADDR=2a01:4f8:beef:beef::1/64\n\
  IPV6_DEFAULTGW=fe80::1%eth0\nIPV6_AUTOCONF=no\n\
  DNS1=185.12.64.1\nDNS2=185.12.64.2\n"
public-ipv4: 192.168.0.2
public-keys:
- ssh-ed25519 \
  AAAAC3Nzac1lZdI1NTE5AaaAIaFrcac0yVITsmRrmueq6MD0qYNKlEvW8O1Ib4nkhmWh \
  test-key@workstation
vendor_data: "test"
"""
)

USERDATA = b"""#cloud-config
runcmd:
- [touch, /root/cloud-init-worked ]
"""


class TestDataSourceHetzner:
    """
    Test reading the meta-data
    """

    @pytest.fixture
    def ds(self, paths, tmp_path):
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = str(tmp_path)
        ds = DataSourceHetzner.DataSourceHetzner(
            settings.CFG_BUILTIN, distro, paths
        )
        return ds

    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.sources.DataSourceHetzner.EphemeralDHCPv4")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.sources.helpers.hetzner.read_metadata")
    @mock.patch("cloudinit.sources.helpers.hetzner.read_userdata")
    @mock.patch("cloudinit.sources.DataSourceHetzner.get_hcloud_data")
    def test_read_data(
        self,
        m_get_hcloud_data,
        m_usermd,
        m_readmd,
        m_fallback_nic,
        m_net,
        m_dhcp,
        ds,
    ):
        m_get_hcloud_data.return_value = (
            True,
            str(METADATA.get("instance-id")),
        )
        m_readmd.return_value = METADATA.copy()
        m_usermd.return_value = USERDATA
        m_fallback_nic.return_value = "eth0"
        m_dhcp.return_value = [
            {
                "interface": "eth0",
                "fixed-address": "192.168.0.2",
                "routers": "192.168.0.1",
                "subnet-mask": "255.255.255.0",
                "broadcast-address": "192.168.0.255",
            }
        ]

        assert True is ds.get_data()

        m_net.assert_called_once_with(
            ds.distro,
            iface="eth0",
            connectivity_urls_data=[
                {
                    "url": "http://169.254.169.254/hetzner/v1/metadata/instance-id"
                }
            ],
        )

        assert 0 != m_readmd.call_count

        assert METADATA.get("hostname") == ds.get_hostname().hostname

        assert METADATA.get("public-keys") == ds.get_public_ssh_keys()

        assert isinstance(ds.get_public_ssh_keys(), list)
        assert ds.get_userdata_raw() == USERDATA
        assert ds.get_vendordata_raw() == METADATA.get("vendor_data")

    @mock.patch("cloudinit.sources.helpers.hetzner.read_metadata")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.sources.DataSourceHetzner.get_hcloud_data")
    def test_not_on_hetzner_returns_false(
        self, m_get_hcloud_data, m_find_fallback, m_read_md, ds
    ):
        """If helper 'get_hcloud_data' returns False,
        return False from get_data."""
        m_get_hcloud_data.return_value = (False, None)
        ret = ds.get_data()

        assert not ret
        # These are a white box attempt to ensure it did not search.
        assert 0 == m_find_fallback.call_count
        assert 0 == m_read_md.call_count
