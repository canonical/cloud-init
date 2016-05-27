# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Canonical Ltd.
#
#    Author: Ben Howard <ben.howard@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#   This is a testcase for the SmartOS datasource. It replicates a serial
#   console and acts like the SmartOS console does in order to validate
#   return responses.
#

from __future__ import print_function

from binascii import crc32
import json
import os
import os.path
import re
import shutil
import stat
import tempfile
import uuid

import serial
import six

from cloudinit import helpers as c_helpers
from cloudinit.sources import DataSourceSmartOS
from cloudinit.util import b64e

from ..helpers import mock, FilesystemMockingTestCase, TestCase

SDC_NICS = json.loads("""
[
    {
        "nic_tag": "external",
        "primary": true,
        "mtu": 1500,
        "model": "virtio",
        "gateway": "8.12.42.1",
        "netmask": "255.255.255.0",
        "ip": "8.12.42.102",
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "gateways": [
            "8.12.42.1"
        ],
        "vlan_id": 324,
        "mac": "90:b8:d0:f5:e4:f5",
        "interface": "net0",
        "ips": [
            "8.12.42.102/24"
        ]
    },
    {
        "nic_tag": "sdc_overlay/16187209",
        "gateway": "192.168.128.1",
        "model": "virtio",
        "mac": "90:b8:d0:a5:ff:cd",
        "netmask": "255.255.252.0",
        "ip": "192.168.128.93",
        "network_uuid": "4cad71da-09bc-452b-986d-03562a03a0a9",
        "gateways": [
            "192.168.128.1"
        ],
        "vlan_id": 2,
        "mtu": 8500,
        "interface": "net1",
        "ips": [
            "192.168.128.93/22"
        ]
    }
]
""")

MOCK_RETURNS = {
    'hostname': 'test-host',
    'root_authorized_keys': 'ssh-rsa AAAAB3Nz...aC1yc2E= keyname',
    'disable_iptables_flag': None,
    'enable_motd_sys_info': None,
    'test-var1': 'some data',
    'cloud-init:user-data': '\n'.join(['#!/bin/sh', '/bin/true', '']),
    'sdc:datacenter_name': 'somewhere2',
    'sdc:operator-script': '\n'.join(['bin/true', '']),
    'sdc:uuid': str(uuid.uuid4()),
    'sdc:vendor-data': '\n'.join(['VENDOR_DATA', '']),
    'user-data': '\n'.join(['something', '']),
    'user-script': '\n'.join(['/bin/true', '']),
    'sdc:nics': json.dumps(SDC_NICS),
}

DMI_DATA_RETURN = 'smartdc'


class PsuedoJoyentClient(object):
    def __init__(self, data=None):
        if data is None:
            data = MOCK_RETURNS.copy()
        self.data = data
        return

    def get(self, key, default=None, strip=False):
        if key in self.data:
            r = self.data[key]
            if strip:
                r = r.strip()
        else:
            r = default
        return r

    def get_json(self, key, default=None):
        result = self.get(key, default=default)
        if result is None:
            return default
        return json.loads(result)

    def exists(self):
        return True


class TestSmartOSDataSource(FilesystemMockingTestCase):
    def setUp(self):
        super(TestSmartOSDataSource, self).setUp()

        dsmos = 'cloudinit.sources.DataSourceSmartOS'
        patcher = mock.patch(dsmos + ".jmc_client_factory")
        self.jmc_cfact = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch(dsmos + ".get_smartos_environ")
        self.get_smartos_environ = patcher.start()
        self.addCleanup(patcher.stop)

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.paths = c_helpers.Paths({'cloud_dir': self.tmp})

        self.legacy_user_d = tempfile.mkdtemp()
        self.orig_lud = DataSourceSmartOS.LEGACY_USER_D
        DataSourceSmartOS.LEGACY_USER_D = self.legacy_user_d

    def tearDown(self):
        DataSourceSmartOS.LEGACY_USER_D = self.orig_lud
        super(TestSmartOSDataSource, self).tearDown()

    def _get_ds(self, mockdata=None, mode=DataSourceSmartOS.SMARTOS_ENV_KVM,
                sys_cfg=None, ds_cfg=None):
        self.jmc_cfact.return_value = PsuedoJoyentClient(mockdata)
        self.get_smartos_environ.return_value = mode

        if sys_cfg is None:
            sys_cfg = {}

        if ds_cfg is not None:
            sys_cfg['datasource'] = sys_cfg.get('datasource', {})
            sys_cfg['datasource']['SmartOS'] = ds_cfg

        return DataSourceSmartOS.DataSourceSmartOS(
            sys_cfg, distro=None, paths=self.paths)

    def test_no_base64(self):
        ds_cfg = {'no_base64_decode': ['test_var1'], 'all_base': True}
        dsrc = self._get_ds(ds_cfg=ds_cfg)
        ret = dsrc.get_data()
        self.assertTrue(ret)

    def test_uuid(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['sdc:uuid'],
                         dsrc.metadata['instance-id'])

    def test_root_keys(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['root_authorized_keys'],
                         dsrc.metadata['public-keys'])

    def test_hostname_b64(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['hostname'],
                         dsrc.metadata['local-hostname'])

    def test_hostname(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['hostname'],
                         dsrc.metadata['local-hostname'])

    def test_userdata(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['user-data'],
                         dsrc.metadata['legacy-user-data'])
        self.assertEqual(MOCK_RETURNS['cloud-init:user-data'],
                         dsrc.userdata_raw)

    def test_sdc_nics(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(json.loads(MOCK_RETURNS['sdc:nics']),
                          dsrc.metadata['network-data'])

    def test_sdc_scripts(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['user-script'],
                         dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        self.assertEqual(user_script_perm, '700')

    def test_scripts_shebanged(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['user-script'],
                         dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        shebang = None
        with open(legacy_script_f, 'r') as f:
            shebang = f.readlines()[0].strip()
        self.assertEqual(shebang, "#!/bin/bash")
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        self.assertEqual(user_script_perm, '700')

    def test_scripts_shebang_not_added(self):
        """
            Test that the SmartOS requirement that plain text scripts
            are executable. This test makes sure that plain texts scripts
            with out file magic have it added appropriately by cloud-init.
        """

        my_returns = MOCK_RETURNS.copy()
        my_returns['user-script'] = '\n'.join(['#!/usr/bin/perl',
                                               'print("hi")', ''])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(my_returns['user-script'],
                         dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        shebang = None
        with open(legacy_script_f, 'r') as f:
            shebang = f.readlines()[0].strip()
        self.assertEqual(shebang, "#!/usr/bin/perl")

    def test_userdata_removed(self):
        """
            User-data in the SmartOS world is supposed to be written to a file
            each and every boot. This tests to make sure that in the event the
            legacy user-data is removed, the existing user-data is backed-up
            and there is no /var/db/user-data left.
        """

        user_data_f = "%s/mdata-user-data" % self.legacy_user_d
        with open(user_data_f, 'w') as f:
            f.write("PREVIOUS")

        my_returns = MOCK_RETURNS.copy()
        del my_returns['user-data']

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertFalse(dsrc.metadata.get('legacy-user-data'))

        found_new = False
        for root, _dirs, files in os.walk(self.legacy_user_d):
            for name in files:
                name_f = os.path.join(root, name)
                permissions = oct(os.stat(name_f)[stat.ST_MODE])[-3:]
                if re.match(r'.*\/mdata-user-data$', name_f):
                    found_new = True
                    print(name_f)
                    self.assertEqual(permissions, '400')

        self.assertFalse(found_new)

    def test_vendor_data_not_default(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['sdc:vendor-data'],
                         dsrc.metadata['vendor-data'])

    def test_default_vendor_data(self):
        my_returns = MOCK_RETURNS.copy()
        def_op_script = my_returns['sdc:vendor-data']
        del my_returns['sdc:vendor-data']
        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertNotEqual(def_op_script, dsrc.metadata['vendor-data'])

        # we expect default vendor-data is a boothook
        self.assertTrue(dsrc.vendordata_raw.startswith("#cloud-boothook"))

    def test_disable_iptables_flag(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['disable_iptables_flag'],
                         dsrc.metadata['iptables_disable'])

    def test_motd_sys_info(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(MOCK_RETURNS['enable_motd_sys_info'],
                         dsrc.metadata['motd_sys_info'])

    def test_default_ephemeral(self):
        # Test to make sure that the builtin config has the ephemeral
        # configuration.
        dsrc = self._get_ds()
        cfg = dsrc.get_config_obj()

        ret = dsrc.get_data()
        self.assertTrue(ret)

        assert 'disk_setup' in cfg
        assert 'fs_setup' in cfg
        self.assertIsInstance(cfg['disk_setup'], dict)
        self.assertIsInstance(cfg['fs_setup'], list)

    def test_override_disk_aliases(self):
        # Test to make sure that the built-in DS is overriden
        builtin = DataSourceSmartOS.BUILTIN_DS_CONFIG

        mydscfg = {'disk_aliases': {'FOO': '/dev/bar'}}

        # expect that these values are in builtin, or this is pointless
        for k in mydscfg:
            self.assertIn(k, builtin)

        dsrc = self._get_ds(ds_cfg=mydscfg)
        ret = dsrc.get_data()
        self.assertTrue(ret)

        self.assertEqual(mydscfg['disk_aliases']['FOO'],
                         dsrc.ds_cfg['disk_aliases']['FOO'])

        self.assertEqual(dsrc.device_name_to_device('FOO'),
                         mydscfg['disk_aliases']['FOO'])


class TestJoyentMetadataClient(FilesystemMockingTestCase):

    def setUp(self):
        super(TestJoyentMetadataClient, self).setUp()
        self.serial = mock.MagicMock(spec=serial.Serial)
        self.request_id = 0xabcdef12
        self.metadata_value = 'value'
        self.response_parts = {
            'command': 'SUCCESS',
            'crc': 'b5a9ff00',
            'length': 17 + len(b64e(self.metadata_value)),
            'payload': b64e(self.metadata_value),
            'request_id': '{0:08x}'.format(self.request_id),
        }

        def make_response():
            payloadstr = ''
            if 'payload' in self.response_parts:
                payloadstr = ' {0}'.format(self.response_parts['payload'])
            return ('V2 {length} {crc} {request_id} '
                    '{command}{payloadstr}\n'.format(
                        payloadstr=payloadstr,
                        **self.response_parts).encode('ascii'))

        self.metasource_data = None

        def read_response(length):
            if not self.metasource_data:
                self.metasource_data = make_response()
                self.metasource_data_len = len(self.metasource_data)
            resp = self.metasource_data[:length]
            self.metasource_data = self.metasource_data[length:]
            return resp

        self.serial.read.side_effect = read_response
        self.patched_funcs.enter_context(
            mock.patch('cloudinit.sources.DataSourceSmartOS.random.randint',
                       mock.Mock(return_value=self.request_id)))

    def _get_client(self):
        return DataSourceSmartOS.JoyentMetadataClient(
            fp=self.serial, smartos_type=DataSourceSmartOS.SMARTOS_ENV_KVM)

    def assertEndsWith(self, haystack, prefix):
        self.assertTrue(haystack.endswith(prefix),
                        "{0} does not end with '{1}'".format(
                            repr(haystack), prefix))

    def assertStartsWith(self, haystack, prefix):
        self.assertTrue(haystack.startswith(prefix),
                        "{0} does not start with '{1}'".format(
                            repr(haystack), prefix))

    def test_get_metadata_writes_a_single_line(self):
        client = self._get_client()
        client.get('some_key')
        self.assertEqual(1, self.serial.write.call_count)
        written_line = self.serial.write.call_args[0][0]
        print(type(written_line))
        self.assertEndsWith(written_line.decode('ascii'),
                            b'\n'.decode('ascii'))
        self.assertEqual(1, written_line.count(b'\n'))

    def _get_written_line(self, key='some_key'):
        client = self._get_client()
        client.get(key)
        return self.serial.write.call_args[0][0]

    def test_get_metadata_writes_bytes(self):
        self.assertIsInstance(self._get_written_line(), six.binary_type)

    def test_get_metadata_line_starts_with_v2(self):
        foo = self._get_written_line()
        self.assertStartsWith(foo.decode('ascii'), b'V2'.decode('ascii'))

    def test_get_metadata_uses_get_command(self):
        parts = self._get_written_line().decode('ascii').strip().split(' ')
        self.assertEqual('GET', parts[4])

    def test_get_metadata_base64_encodes_argument(self):
        key = 'my_key'
        parts = self._get_written_line(key).decode('ascii').strip().split(' ')
        self.assertEqual(b64e(key), parts[5])

    def test_get_metadata_calculates_length_correctly(self):
        parts = self._get_written_line().decode('ascii').strip().split(' ')
        expected_length = len(' '.join(parts[3:]))
        self.assertEqual(expected_length, int(parts[1]))

    def test_get_metadata_uses_appropriate_request_id(self):
        parts = self._get_written_line().decode('ascii').strip().split(' ')
        request_id = parts[3]
        self.assertEqual(8, len(request_id))
        self.assertEqual(request_id, request_id.lower())

    def test_get_metadata_uses_random_number_for_request_id(self):
        line = self._get_written_line()
        request_id = line.decode('ascii').strip().split(' ')[3]
        self.assertEqual('{0:08x}'.format(self.request_id), request_id)

    def test_get_metadata_checksums_correctly(self):
        parts = self._get_written_line().decode('ascii').strip().split(' ')
        expected_checksum = '{0:08x}'.format(
            crc32(' '.join(parts[3:]).encode('utf-8')) & 0xffffffff)
        checksum = parts[2]
        self.assertEqual(expected_checksum, checksum)

    def test_get_metadata_reads_a_line(self):
        client = self._get_client()
        client.get('some_key')
        self.assertEqual(self.metasource_data_len, self.serial.read.call_count)

    def test_get_metadata_returns_valid_value(self):
        client = self._get_client()
        value = client.get('some_key')
        self.assertEqual(self.metadata_value, value)

    def test_get_metadata_throws_exception_for_incorrect_length(self):
        self.response_parts['length'] = 0
        client = self._get_client()
        self.assertRaises(DataSourceSmartOS.JoyentMetadataFetchException,
                          client.get, 'some_key')

    def test_get_metadata_throws_exception_for_incorrect_crc(self):
        self.response_parts['crc'] = 'deadbeef'
        client = self._get_client()
        self.assertRaises(DataSourceSmartOS.JoyentMetadataFetchException,
                          client.get, 'some_key')

    def test_get_metadata_throws_exception_for_request_id_mismatch(self):
        self.response_parts['request_id'] = 'deadbeef'
        client = self._get_client()
        client._checksum = lambda _: self.response_parts['crc']
        self.assertRaises(DataSourceSmartOS.JoyentMetadataFetchException,
                          client.get, 'some_key')

    def test_get_metadata_returns_None_if_value_not_found(self):
        self.response_parts['payload'] = ''
        self.response_parts['command'] = 'NOTFOUND'
        self.response_parts['length'] = 17
        client = self._get_client()
        client._checksum = lambda _: self.response_parts['crc']
        self.assertIsNone(client.get('some_key'))


class TestNetworkConversion(TestCase):

    def test_convert_simple(self):
        expected = {
            'version': 1,
            'config': [
                {'name': 'net0', 'type': 'physical',
                 'subnets': [{'type': 'static', 'gateway': '8.12.42.1',
                              'netmask': '255.255.255.0',
                              'address': '8.12.42.102/24'}],
                 'mtu': 1500, 'mac_address': '90:b8:d0:f5:e4:f5'},
                {'name': 'net1', 'type': 'physical',
                 'subnets': [{'type': 'static', 'gateway': '192.168.128.1',
                              'netmask': '255.255.252.0',
                              'address': '192.168.128.93/22'}],
                 'mtu': 8500, 'mac_address': '90:b8:d0:a5:ff:cd'}]}
        found = DataSourceSmartOS.convert_smartos_network_data(SDC_NICS)
        self.assertEquals(expected, found)
