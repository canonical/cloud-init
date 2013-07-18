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

from cloudinit import helpers
from cloudinit.sources import DataSourceSmartOS

from mocker import MockerTestCase
import uuid

mock_returns = {
    'hostname': 'test-host',
    'root_authorized_keys': 'ssh-rsa AAAAB3Nz...aC1yc2E= keyname',
    'disable_iptables_flag': False,
    'enable_motd_sys_info': False,
    'system_uuid': str(uuid.uuid4()),
    'smartdc': 'smartdc',
    'userdata': """
#!/bin/sh
/bin/true
""",
}


class MockSerial(object):
    """Fake a serial terminal for testing the code that
        interfaces with the serial"""

    port = None

    def __init__(self):
        self.last = None
        self.last = None
        self.new = True
        self.count = 0
        self.mocked_out = []

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
            if self.last in mock_returns:
                return 'SUCCESS\n'
            else:
                return 'NOTFOUND %s\n' % self.last

        if self.last in mock_returns:
            if not self.mocked_out:
                self.mocked_out = [x for x in self._format_out()]
                print self.mocked_out

            if len(self.mocked_out) > self.count:
                self.count += 1
                return self.mocked_out[self.count - 1]

    def _format_out(self):
        if self.last in mock_returns:
            try:
                for l in mock_returns[self.last].splitlines():
                    yield "%s\n" % l
            except:
                yield "%s\n" % mock_returns[self.last]

            yield '\n'
            yield '.'


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

    def _get_ds(self):

        def _get_serial():
            return MockSerial()

        def _dmi_data():
            return mock_returns['system_uuid'], 'smartdc'

        data = {'sys_cfg': {}}
        mod = DataSourceSmartOS
        self.apply_patches([(mod, 'get_serial', _get_serial)])
        self.apply_patches([(mod, 'dmi_data', _dmi_data)])
        dsrc = mod.DataSourceSmartOS(
            data.get('sys_cfg', {}), distro=None, paths=self.paths)
        return dsrc

    def test_seed(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals('/dev/ttyS1', dsrc.seed)

    def test_issmartdc(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue(dsrc.is_smartdc)

    def test_uuid(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(mock_returns['system_uuid'],
                          dsrc.metadata['instance-id'])

    def test_root_keys(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(mock_returns['root_authorized_keys'],
                          dsrc.metadata['public-keys'])

    def test_hostname(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(mock_returns['hostname'],
                          dsrc.metadata['local-hostname'])

    def test_disable_iptables_flag(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(str(mock_returns['disable_iptables_flag']),
                          dsrc.metadata['iptables_disable'])

    def test_motd_sys_info(self):
        dsrc = self._get_ds()
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEquals(str(mock_returns['enable_motd_sys_info']),
                          dsrc.metadata['motd_sys_info'])


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret
