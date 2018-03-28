# Copyright (C) 2018 Jonas Keidel
#
# Author: Jonas Keidel <jonas.keidel@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.sources import DataSourceHetzner
from cloudinit import util, settings, helpers

from cloudinit.tests.helpers import mock, CiTestCase

METADATA = util.load_yaml("""
hostname: cloudinit-test
instance-id: 123456
local-ipv4: ''
network-config:
  config:
  - mac_address: 96:00:00:08:19:da
    name: eth0
    subnets:
    - dns_nameservers:
      - 213.133.99.99
      - 213.133.100.100
      - 213.133.98.98
      ipv4: true
      type: dhcp
    type: physical
  - name: eth0:0
    subnets:
    - address: 2a01:4f8:beef:beef::1/64
      gateway: fe80::1
      ipv6: true
      routes:
      - gateway: fe80::1%eth0
        netmask: 0
        network: '::'
      type: static
    type: physical
  version: 1
network-sysconfig: "DEVICE='eth0'\nTYPE=Ethernet\nBOOTPROTO=dhcp\n\
  ONBOOT='yes'\nHWADDR=96:00:00:08:19:da\n\
  IPV6INIT=yes\nIPV6ADDR=2a01:4f8:beef:beef::1/64\n\
  IPV6_DEFAULTGW=fe80::1%eth0\nIPV6_AUTOCONF=no\n\
  DNS1=213.133.99.99\nDNS2=213.133.100.100\n"
public-ipv4: 192.168.0.1
public-keys:
- ssh-ed25519 \
  AAAAC3Nzac1lZdI1NTE5AaaAIaFrcac0yVITsmRrmueq6MD0qYNKlEvW8O1Ib4nkhmWh \
  test-key@workstation
vendor_data: "test"
""")

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
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        return ds

    @mock.patch('cloudinit.net.EphemeralIPv4Network')
    @mock.patch('cloudinit.net.find_fallback_nic')
    @mock.patch('cloudinit.sources.helpers.hetzner.read_metadata')
    @mock.patch('cloudinit.sources.helpers.hetzner.read_userdata')
    @mock.patch('cloudinit.sources.DataSourceHetzner.on_hetzner')
    def test_read_data(self, m_on_hetzner, m_usermd, m_readmd, m_fallback_nic,
                       m_net):
        m_on_hetzner.return_value = True
        m_readmd.return_value = METADATA.copy()
        m_usermd.return_value = USERDATA
        m_fallback_nic.return_value = 'eth0'

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        m_net.assert_called_once_with(
            'eth0', '169.254.0.1',
            16, '169.254.255.255'
        )

        self.assertTrue(m_readmd.called)

        self.assertEqual(METADATA.get('hostname'), ds.get_hostname())

        self.assertEqual(METADATA.get('public-keys'),
                         ds.get_public_ssh_keys())

        self.assertIsInstance(ds.get_public_ssh_keys(), list)
        self.assertEqual(ds.get_userdata_raw(), USERDATA)
        self.assertEqual(ds.get_vendordata_raw(), METADATA.get('vendor_data'))

    @mock.patch('cloudinit.sources.helpers.hetzner.read_metadata')
    @mock.patch('cloudinit.net.find_fallback_nic')
    @mock.patch('cloudinit.sources.DataSourceHetzner.on_hetzner')
    def test_not_on_hetzner_returns_false(self, m_on_hetzner, m_find_fallback,
                                          m_read_md):
        """If helper 'on_hetzner' returns False, return False from get_data."""
        m_on_hetzner.return_value = False
        ds = self.get_ds()
        ret = ds.get_data()

        self.assertFalse(ret)
        # These are a white box attempt to ensure it did not search.
        m_find_fallback.assert_not_called()
        m_read_md.assert_not_called()
