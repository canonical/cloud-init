# Copyright (C) 2018 Jonas Keidel
#
# Author: Jonas Keidel <jonas.keidel@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64

import pytest

import cloudinit.sources.helpers.hetzner as hc_helper
from cloudinit import helpers, settings, util
from cloudinit.sources import DataSourceHetzner
from tests.unittests.helpers import CiTestCase, mock

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


class TestDataSourceHetzner(CiTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        super(TestDataSourceHetzner, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self):
        ds = DataSourceHetzner.DataSourceHetzner(
            settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": self.tmp})
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

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        m_net.assert_called_once_with(
            iface="eth0",
            connectivity_url_data={
                "url": "http://169.254.169.254/hetzner/v1/metadata/instance-id"
            },
        )

        self.assertTrue(m_readmd.called)

        self.assertEqual(METADATA.get("hostname"), ds.get_hostname())

        self.assertEqual(METADATA.get("public-keys"), ds.get_public_ssh_keys())

        self.assertIsInstance(ds.get_public_ssh_keys(), list)
        self.assertEqual(ds.get_userdata_raw(), USERDATA)
        self.assertEqual(ds.get_vendordata_raw(), METADATA.get("vendor_data"))

    @mock.patch("cloudinit.sources.helpers.hetzner.read_metadata")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.sources.DataSourceHetzner.get_hcloud_data")
    def test_not_on_hetzner_returns_false(
        self, m_get_hcloud_data, m_find_fallback, m_read_md
    ):
        """If helper 'get_hcloud_data' returns False,
        return False from get_data."""
        m_get_hcloud_data.return_value = (False, None)
        ds = self.get_ds()
        ret = ds.get_data()

        self.assertFalse(ret)
        # These are a white box attempt to ensure it did not search.
        m_find_fallback.assert_not_called()
        m_read_md.assert_not_called()


class TestMaybeB64Decode:
    """Test the maybe_b64decode helper function."""

    @pytest.mark.parametrize("invalid_input", (str("not bytes"), int(4)))
    def test_raises_error_on_non_bytes(self, invalid_input):
        """maybe_b64decode should raise error if data is not bytes."""
        with pytest.raises(TypeError):
            hc_helper.maybe_b64decode(invalid_input)

    @pytest.mark.parametrize(
        "in_data,expected",
        [
            # If data is not b64 encoded, then return value should be the same.
            (b"this is my data", b"this is my data"),
            # If data is b64 encoded, then return value should be decoded.
            (base64.b64encode(b"data"), b"data"),
        ],
    )
    def test_happy_path(self, in_data, expected):
        assert expected == hc_helper.maybe_b64decode(in_data)
