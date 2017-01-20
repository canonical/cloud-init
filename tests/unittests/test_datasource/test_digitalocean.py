# Copyright (C) 2014 Neal Shrader
#
# Author: Neal Shrader <neal@digitalocean.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceDigitalOcean
from cloudinit.sources.helpers import digitalocean

from ..helpers import mock, TestCase

DO_MULTIPLE_KEYS = ["ssh-rsa AAAAB3NzaC1yc2EAAAA... test1@do.co",
                    "ssh-rsa AAAAB3NzaC1yc2EAAAA... test2@do.co"]
DO_SINGLE_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAA... test@do.co"

# the following JSON was taken from droplet (that's why its a string)
DO_META = json.loads("""
{
  "droplet_id": "22532410",
  "hostname": "utl-96268",
  "vendor_data": "vendordata goes here",
  "user_data": "userdata goes here",
  "public_keys": "",
  "auth_key": "authorization_key",
  "region": "nyc3",
  "interfaces": {
    "private": [
      {
        "ipv4": {
          "ip_address": "10.132.6.205",
          "netmask": "255.255.0.0",
          "gateway": "10.132.0.1"
        },
        "mac": "04:01:57:d1:9e:02",
        "type": "private"
      }
    ],
    "public": [
      {
        "ipv4": {
          "ip_address": "192.0.0.20",
          "netmask": "255.255.255.0",
          "gateway": "104.236.0.1"
        },
        "ipv6": {
          "ip_address": "2604:A880:0800:0000:1000:0000:0000:0000",
          "cidr": 64,
          "gateway": "2604:A880:0800:0000:0000:0000:0000:0001"
        },
        "anchor_ipv4": {
          "ip_address": "10.0.0.5",
          "netmask": "255.255.0.0",
          "gateway": "10.0.0.1"
        },
        "mac": "04:01:57:d1:9e:01",
        "type": "public"
      }
    ]
  },
  "floating_ip": {
    "ipv4": {
      "active": false
    }
  },
  "dns": {
    "nameservers": [
      "2001:4860:4860::8844",
      "2001:4860:4860::8888",
      "8.8.8.8"
    ]
  }
}
""")

# This has no private interface
DO_META_2 = {
    "droplet_id": 27223699,
    "hostname": "smtest1",
    "vendor_data": "\n".join([
        ('"Content-Type: multipart/mixed; '
         'boundary=\"===============8645434374073493512==\"'),
        'MIME-Version: 1.0',
        '',
        '--===============8645434374073493512==',
        'MIME-Version: 1.0'
        'Content-Type: text/cloud-config; charset="us-ascii"'
        'Content-Transfer-Encoding: 7bit'
        'Content-Disposition: attachment; filename="cloud-config"'
        '',
        '#cloud-config',
        'disable_root: false',
        'manage_etc_hosts: true',
        '',
        '',
        '--===============8645434374073493512=='
    ]),
    "public_keys": [
        "ssh-rsa AAAAB3NzaN...N3NtHw== smoser@brickies"
    ],
    "auth_key": "88888888888888888888888888888888",
    "region": "nyc3",
    "interfaces": {
        "public": [{
            "ipv4": {
                "ip_address": "45.55.249.133",
                "netmask": "255.255.192.0",
                "gateway": "45.55.192.1"
            },
            "anchor_ipv4": {
                "ip_address": "10.17.0.5",
                "netmask": "255.255.0.0",
                "gateway": "10.17.0.1"
            },
            "mac": "ae:cc:08:7c:88:00",
            "type": "public"
        }]
    },
    "floating_ip": {"ipv4": {"active": True, "ip_address": "138.197.59.92"}},
    "dns": {"nameservers": ["8.8.8.8", "8.8.4.4"]},
    "tags": None,
}

DO_META['public_keys'] = DO_SINGLE_KEY

MD_URL = 'http://169.254.169.254/metadata/v1.json'


def _mock_dmi():
    return (True, DO_META.get('id'))


class TestDataSourceDigitalOcean(TestCase):
    """
    Test reading the meta-data
    """

    def get_ds(self, get_sysinfo=_mock_dmi):
        ds = DataSourceDigitalOcean.DataSourceDigitalOcean(
            settings.CFG_BUILTIN, None, helpers.Paths({}))
        ds.use_ip4LL = False
        if get_sysinfo is not None:
            ds._get_sysinfo = get_sysinfo
        return ds

    @mock.patch('cloudinit.sources.helpers.digitalocean.read_sysinfo')
    def test_returns_false_not_on_docean(self, m_read_sysinfo):
        m_read_sysinfo.return_value = (False, None)
        ds = self.get_ds(get_sysinfo=None)
        self.assertEqual(False, ds.get_data())
        self.assertTrue(m_read_sysinfo.called)

    @mock.patch('cloudinit.sources.helpers.digitalocean.read_metadata')
    def test_metadata(self, mock_readmd):
        mock_readmd.return_value = DO_META.copy()

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(mock_readmd.called)

        self.assertEqual(DO_META.get('user_data'), ds.get_userdata_raw())
        self.assertEqual(DO_META.get('vendor_data'), ds.get_vendordata_raw())
        self.assertEqual(DO_META.get('region'), ds.availability_zone)
        self.assertEqual(DO_META.get('droplet_id'), ds.get_instance_id())
        self.assertEqual(DO_META.get('hostname'), ds.get_hostname())

        # Single key
        self.assertEqual([DO_META.get('public_keys')],
                         ds.get_public_ssh_keys())

        self.assertIsInstance(ds.get_public_ssh_keys(), list)

    @mock.patch('cloudinit.sources.helpers.digitalocean.read_metadata')
    def test_multiple_ssh_keys(self, mock_readmd):
        metadata = DO_META.copy()
        metadata['public_keys'] = DO_MULTIPLE_KEYS
        mock_readmd.return_value = metadata.copy()

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(mock_readmd.called)

        # Multiple keys
        self.assertEqual(metadata['public_keys'], ds.get_public_ssh_keys())
        self.assertIsInstance(ds.get_public_ssh_keys(), list)


class TestNetworkConvert(TestCase):

    def _get_networking(self):
        netcfg = digitalocean.convert_network_configuration(
            DO_META['interfaces'], DO_META['dns']['nameservers'])
        self.assertIn('config', netcfg)
        return netcfg

    def test_networking_defined(self):
        netcfg = self._get_networking()
        self.assertIsNotNone(netcfg)

        for nic_def in netcfg.get('config'):
            print(json.dumps(nic_def, indent=3))
            n_type = nic_def.get('type')
            n_subnets = nic_def.get('type')
            n_name = nic_def.get('name')
            n_mac = nic_def.get('mac_address')

            self.assertIsNotNone(n_type)
            self.assertIsNotNone(n_subnets)
            self.assertIsNotNone(n_name)
            self.assertIsNotNone(n_mac)

    def _get_nic_definition(self, int_type, expected_name):
        """helper function to return if_type (i.e. public) and the expected
           name used by cloud-init (i.e eth0)"""
        netcfg = self._get_networking()
        meta_def = (DO_META.get('interfaces')).get(int_type)[0]

        self.assertEqual(int_type, meta_def.get('type'))

        for nic_def in netcfg.get('config'):
            print(nic_def)
            if nic_def.get('name') == expected_name:
                return nic_def, meta_def

    def _get_match_subn(self, subnets, ip_addr):
        """get the matching subnet definition based on ip address"""
        for subn in subnets:
            address = subn.get('address')
            self.assertIsNotNone(address)

            # equals won't work because of ipv6 addressing being in
            # cidr notation, i.e fe00::1/64
            if ip_addr in address:
                print(json.dumps(subn, indent=3))
                return subn

    def test_public_interface_defined(self):
        """test that the public interface is defined as eth0"""
        (nic_def, meta_def) = self._get_nic_definition('public', 'eth0')
        self.assertEqual('eth0', nic_def.get('name'))
        self.assertEqual(meta_def.get('mac'), nic_def.get('mac_address'))
        self.assertEqual('physical', nic_def.get('type'))

    def test_private_interface_defined(self):
        """test that the private interface is defined as eth1"""
        (nic_def, meta_def) = self._get_nic_definition('private', 'eth1')
        self.assertEqual('eth1', nic_def.get('name'))
        self.assertEqual(meta_def.get('mac'), nic_def.get('mac_address'))
        self.assertEqual('physical', nic_def.get('type'))

    def _check_dns_nameservers(self, subn_def):
        self.assertIn('dns_nameservers', subn_def)
        expected_nameservers = DO_META['dns']['nameservers']
        nic_nameservers = subn_def.get('dns_nameservers')
        self.assertEqual(expected_nameservers, nic_nameservers)

    def test_public_interface_ipv6(self):
        """test public ipv6 addressing"""
        (nic_def, meta_def) = self._get_nic_definition('public', 'eth0')
        ipv6_def = meta_def.get('ipv6')
        self.assertIsNotNone(ipv6_def)

        subn_def = self._get_match_subn(nic_def.get('subnets'),
                                        ipv6_def.get('ip_address'))

        cidr_notated_address = "{0}/{1}".format(ipv6_def.get('ip_address'),
                                                ipv6_def.get('cidr'))

        self.assertEqual(cidr_notated_address, subn_def.get('address'))
        self.assertEqual(ipv6_def.get('gateway'), subn_def.get('gateway'))
        self._check_dns_nameservers(subn_def)

    def test_public_interface_ipv4(self):
        """test public ipv4 addressing"""
        (nic_def, meta_def) = self._get_nic_definition('public', 'eth0')
        ipv4_def = meta_def.get('ipv4')
        self.assertIsNotNone(ipv4_def)

        subn_def = self._get_match_subn(nic_def.get('subnets'),
                                        ipv4_def.get('ip_address'))

        self.assertEqual(ipv4_def.get('netmask'), subn_def.get('netmask'))
        self.assertEqual(ipv4_def.get('gateway'), subn_def.get('gateway'))
        self._check_dns_nameservers(subn_def)

    def test_public_interface_anchor_ipv4(self):
        """test public ipv4 addressing"""
        (nic_def, meta_def) = self._get_nic_definition('public', 'eth0')
        ipv4_def = meta_def.get('anchor_ipv4')
        self.assertIsNotNone(ipv4_def)

        subn_def = self._get_match_subn(nic_def.get('subnets'),
                                        ipv4_def.get('ip_address'))

        self.assertEqual(ipv4_def.get('netmask'), subn_def.get('netmask'))
        self.assertNotIn('gateway', subn_def)

    def test_convert_without_private(self):
        netcfg = digitalocean.convert_network_configuration(
            DO_META_2['interfaces'], DO_META_2['dns']['nameservers'])

        byname = {}
        for i in netcfg['config']:
            if 'name' in i:
                if i['name'] in byname:
                    raise ValueError("name '%s' in config twice: %s" %
                                     (i['name'], netcfg))
                byname[i['name']] = i
        self.assertTrue('eth0' in byname)
        self.assertTrue('subnets' in byname['eth0'])
        eth0 = byname['eth0']
        self.assertEqual(
            sorted(['45.55.249.133', '10.17.0.5']),
            sorted([i['address'] for i in eth0['subnets']]))

# vi: ts=4 expandtab
