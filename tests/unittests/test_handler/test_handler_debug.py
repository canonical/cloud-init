# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Yahoo! Inc.
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

from cloudinit.config import cc_debug

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNone

from .. import helpers as t_help

import logging

LOG = logging.getLogger(__name__)


class TestDebug(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestDebug, self).setUp()
        self.new_root = self.makeDir(prefix="unittest_")

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        d = cls(distro, {}, paths)
        ds = DataSourceNone.DataSourceNone({}, d, paths)
        if metadata:
            ds.metadata.update(metadata)
        return cloud.Cloud(ds, paths, {}, d, None)

    def test_debug_write(self):
        cfg = {
            'abc': '123',
            'c': u'\u20a0',
            'debug': {
                'verbose': True,
                # Does not actually write here due to mocking...
                'output': '/var/log/cloud-init-debug.log',
            },
        }
        cc = self._get_cloud('ubuntu')
        cc_debug.handle('cc_debug', cfg, cc, LOG, [])
        contents = util.load_file('/var/log/cloud-init-debug.log')
        # Some basic sanity tests...
        self.assertGreater(len(contents), 0)
        for k in cfg.keys():
            self.assertIn(k, contents)

    def test_debug_no_write(self):
        cfg = {
            'abc': '123',
            'debug': {
                'verbose': False,
                # Does not actually write here due to mocking...
                'output': '/var/log/cloud-init-debug.log',
            },
        }
        cc = self._get_cloud('ubuntu')
        cc_debug.handle('cc_debug', cfg, cc, LOG, [])
        self.assertRaises(IOError,
                          util.load_file, '/var/log/cloud-init-debug.log')
