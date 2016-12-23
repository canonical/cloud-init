# Copyright (C) 2014 Yahoo! Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_debug

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNone

from .. import helpers as t_help

import logging
import shutil
import tempfile

LOG = logging.getLogger(__name__)


class TestDebug(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestDebug, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

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
        self.assertNotEqual(0, len(contents))
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

# vi: ts=4 expandtab
