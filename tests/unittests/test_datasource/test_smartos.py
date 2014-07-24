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
from cloudinit import helpers as c_helpers
from cloudinit.sources import DataSourceSmartOS
from .. import helpers
import os
import os.path
import re
import stat
import uuid

MOCK_RETURNS = {
    'hostname': 'test-host',
    'root_authorized_keys': 'ssh-rsa AAAAB3Nz...aC1yc2E= keyname',
    'disable_iptables_flag': None,
    'enable_motd_sys_info': None,
    'test-var1': 'some data',
    'cloud-init:user-data': '\n'.join(['#!/bin/sh', '/bin/true', '']),
    'sdc:datacenter_name': 'somewhere2',
    'sdc:operator-script': '\n'.join(['bin/true', '']),
    'sdc:vendor-data': '\n'.join(['VENDOR_DATA', '']),
    'user-data': '\n'.join(['something', '']),
    'user-script': '\n'.join(['/bin/true', '']),
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


class TestSmartOSDataSource(helpers.FilesystemMockingTestCase):
    def setUp(self):
        helpers.FilesystemMockingTestCase.setUp(self)

        # makeDir comes from MockerTestCase
        self.tmp = self.makeDir()
        self.legacy_user_d = self.makeDir()

        # If you should want to watch the logs...
        self._log = None
        self._log_file = None
        self._log_handler = None

        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        self.paths = c_helpers.Paths({'cloud_dir': self.tmp})

        self.unapply = []
        super(TestSmartOSDataSource, self).setUp()

    def tearDown(self):
        helpers.FilesystemMockingTestCase.tearDown(self)
        if self._log_handler and self._log:
            self._log.removeHandler(self._log_handler)
        apply_patches([i for i in reversed(self.unapply)])
        super(TestSmartOSDataSource, self).tearDown()

    def _patchIn(self, root):
        self.restore()
        self.patchOS(root)
        self.patchUtils(root)

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

        def _os_uname():
            # LP: #1243287. tests assume this runs, but running test on
            # arm would cause them all to fail.
            return ('LINUX', 'NODENAME', 'RELEASE', 'VERSION', 'x86_64')

        if sys_cfg is None:
            sys_cfg = {}

        if ds_cfg is not None:
            sys_cfg['datasource'] = sys_cfg.get('datasource', {})
            sys_cfg['datasource']['SmartOS'] = ds_cfg

        self.apply_patches([(mod, 'LEGACY_USER_D', self.legacy_user_d)])
        self.apply_patches([(mod, 'get_serial', _get_serial)])
        self.apply_patches([(mod, 'dmi_data', _dmi_data)])
        self.apply_patches([(os, 'uname', _os_uname)])
        self.apply_patches([(mod, 'device_exists', lambda d: True)])
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
        for k in ('hostname', 'cloud-init:user-data'):
            my_returns[k] = base64.b64encode(my_returns[k])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])
        self.assertEquals(MOCK_RETURNS['cloud-init:user-data'],
                          dsrc.userdata_raw)
        self.assertEquals(MOCK_RETURNS['root_authorized_keys'],
                          dsrc.metadata['public-keys'])
        self.assertEquals(MOCK_RETURNS['disable_iptables_flag'],
                          dsrc.metadata['iptables_disable'])
        self.assertEquals(MOCK_RETURNS['enable_motd_sys_info'],
                          dsrc.metadata['motd_sys_info'])

    def test_b64_userdata(self):
        my_returns = MOCK_RETURNS.copy()
        my_returns['b64-cloud-init:user-data'] = "true"
        my_returns['b64-hostname'] = "true"
        for k in ('hostname', 'cloud-init:user-data'):
            my_returns[k] = base64.b64encode(my_returns[k])

        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['hostname'],
                          dsrc.metadata['local-hostname'])
        self.assertEquals(MOCK_RETURNS['cloud-init:user-data'],
                          dsrc.userdata_raw)
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
        self.assertEquals(MOCK_RETURNS['cloud-init:user-data'],
                          dsrc.userdata_raw)

    def test_userdata(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['user-data'],
                          dsrc.metadata['legacy-user-data'])
        self.assertEquals(MOCK_RETURNS['cloud-init:user-data'],
                          dsrc.userdata_raw)

    def test_sdc_scripts(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['user-script'],
                          dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        self.assertEquals(user_script_perm, '700')

    def test_scripts_shebanged(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['user-script'],
                          dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        shebang = None
        with open(legacy_script_f, 'r') as f:
            shebang = f.readlines()[0].strip()
        self.assertEquals(shebang, "#!/bin/bash")
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        self.assertEquals(user_script_perm, '700')

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
        self.assertEquals(my_returns['user-script'],
                          dsrc.metadata['user-script'])

        legacy_script_f = "%s/user-script" % self.legacy_user_d
        self.assertTrue(os.path.exists(legacy_script_f))
        self.assertTrue(os.path.islink(legacy_script_f))
        shebang = None
        with open(legacy_script_f, 'r') as f:
            shebang = f.readlines()[0].strip()
        self.assertEquals(shebang, "#!/usr/bin/perl")

    def test_userdata_removed(self):
        """
            User-data in the SmartOS world is supposed to be written to a file
            each and every boot. This tests to make sure that in the event the
            legacy user-data is removed, the existing user-data is backed-up and
            there is no /var/db/user-data left.
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
                    print name_f
                    self.assertEquals(permissions, '400')

        self.assertFalse(found_new)

    def test_vendor_data_not_default(self):
        dsrc = self._get_ds(mockdata=MOCK_RETURNS)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(MOCK_RETURNS['sdc:vendor-data'],
                          dsrc.metadata['vendor-data'])

    def test_default_vendor_data(self):
        my_returns = MOCK_RETURNS.copy()
        def_op_script = my_returns['sdc:vendor-data']
        del my_returns['sdc:vendor-data']
        dsrc = self._get_ds(mockdata=my_returns)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertNotEquals(def_op_script, dsrc.metadata['vendor-data'])

        # we expect default vendor-data is a boothook
        self.assertTrue(dsrc.vendordata_raw.startswith("#cloud-boothook"))

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
