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

import base64
from cloudinit import helpers
from cloudinit.sources import DataSourceSmartOS

from mocker import MockerTestCase
import uuid

MOCK_RETURNS = {
    'hostname': 'test-host',
    'root_authorized_keys': 'ssh-rsa AAAAB3Nz...aC1yc2E= keyname',
    'disable_iptables_flag': None,
    'enable_motd_sys_info': None,
    'test-var1': 'some data',
    'user-data': '\n'.join(['#!/bin/sh', '/bin/true', '']),
}

DMI_DATA_RETURN = (str(uuid.uuid4()), 'smartdc')


class MockSerial(object):
    """Fake a serial terminal for testing the code that
        interfaces with the serial"""

    port = None

    def __init__(self, mockdata):
        self.last = None
        self.last = None
        self.new = True
        self.count = 0
        self.mocked_out = []
        self.mockdata = mockdata

    def open(self):
        return True

    def close(self):
        return True

    def isOpen(self):
        return True

    def write(self, line):
        line = line.replace('GET ', '')
        self.last = line.rstrip()

    def readline(self):
        if self.new:
            self.new = False
            if self.last in self.mockdata:
                return 'SUCCESS\n'
            else:
                return 'NOTFOUND %s\n' % self.last

        if self.last in self.mockdata:
            if not self.mocked_out:
                self.mocked_out = [x for x in self._format_out()]

            if len(self.mocked_out) > self.count:
                self.count += 1
                return self.mocked_out[self.count - 1]

    def _format_out(self):
        if self.last in self.mockdata:
            _mret = self.mockdata[self.last]
            try:
                for l in _mret.splitlines():
                    yield "%s\n" % l.rstrip()
            except:
                yield "%s\n" % _mret.rstrip()

            yield '.'
            yield '\n'


class TestSmartOSDataSource(MockerTestCase):
    def setUp(self):
        # makeDir comes from MockerTestCase
        self.tmp = self.makeDir()

        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        self.paths = helpers.Paths({'cloud_dir': self.tmp})

        self.unapply = []
        super(TestSmartOSDataSource, self).setUp()

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])
        super(TestSmartOSDataSource, self).tearDown()

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

    def _get_ds(self, sys_cfg=None, ds_cfg=None, mockdata=None, dmi_data=None):
        mod = DataSourceSmartOS

        if mockdata is None:
            mockdata = MOCK_RETURNS

        if dmi_data is None:
            dmi_data = DMI_DATA_RETURN

        def _get_serial(*_):
            return MockSerial(mockdata)

        def _dmi_data():
            return dmi_data

        if sys_cfg is None:
            sys_cfg = {}

        if ds_cfg is not None:
            sys_cfg['datasource'] = sys_cfg.get('datasource', {})
            sys_cfg['datasource']['SmartOS'] = ds_cfg

        self.apply_patches([(mod, 'get_serial', _get_serial)])
        self.apply_patches([(mod, 'dmi_data', _dmi_data)])
        dsrc = mod.DataSourceSmartOS(sys_cfg, distro=None,
                                     paths=self.paths)
        return dsrc

    def test_seed(self):
        # default seed should be /dev/ttyS1
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals('/dev/ttyS1', dsrc.seed)

    def test_issmartdc(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue(dsrc.is_smartdc)

    def test_no_base64(self):
        ds_cfg = {'no_base64_decode': ['test_var1'], 'all_base': True}
        dsrc = self._get_ds(ds_cfg=ds_cfg)
        ret = dsrc.get_data()
        self.assertTrue(ret)

    def test_uuid(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(DMI_DATA_RETURN[0], dsrc.metadata['instance-id'])

    def test_root_keys(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['root_authorized_keys'],
                          dsrc.metadata['public-keys'])

    def test_hostname_b64(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])

    def test_hostname(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])

    def test_base64_all(self):
        # metadata provided base64_all of true
        my_returns = MOCK_RETURNS.copy()
        my_returns['base64_all'] = "true"
        for k in ('hostname', 'user-data'):
            my_returns[k] = base64.b64encode(my_returns[k])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])
        self.assertEquals(MOCK_RETURNS['user-data'],
                          dsrc.userdata_raw)
        self.assertEquals(MOCK_RETURNS['root_authorized_keys'],
                          dsrc.metadata['public-keys'])
        self.assertEquals(MOCK_RETURNS['disable_iptables_flag'],
                          dsrc.metadata['iptables_disable'])
        self.assertEquals(MOCK_RETURNS['enable_motd_sys_info'],
                          dsrc.metadata['motd_sys_info'])

    def test_b64_userdata(self):
        my_returns = MOCK_RETURNS.copy()
        my_returns['b64-user-data'] = "true"
        my_returns['b64-hostname'] = "true"
        for k in ('hostname', 'user-data'):
            my_returns[k] = base64.b64encode(my_returns[k])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])
        self.assertEquals(MOCK_RETURNS['user-data'], dsrc.userdata_raw)
        self.assertEquals(MOCK_RETURNS['root_authorized_keys'],
                          dsrc.metadata['public-keys'])

    def test_b64_keys(self):
        my_returns = MOCK_RETURNS.copy()
        my_returns['base64_keys'] = 'hostname,ignored'
        for k in ('hostname',):
            my_returns[k] = base64.b64encode(my_returns[k])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])
        self.assertEquals(MOCK_RETURNS['user-data'], dsrc.userdata_raw)

    def test_userdata(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['user-data'], dsrc.userdata_raw)

    def test_disable_iptables_flag(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['disable_iptables_flag'],
                          dsrc.metadata['iptables_disable'])

    def test_motd_sys_info(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['enable_motd_sys_info'],
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


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret
