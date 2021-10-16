# Copyright (C) 2014 Yahoo! Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import shutil
import tempfile

from cloudinit import util
from cloudinit.config import cc_debug
from cloudinit.tests.helpers import (FilesystemMockingTestCase, mock)

from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@mock.patch('cloudinit.distros.debian.read_system_locale')
class TestDebug(FilesystemMockingTestCase):
    def setUp(self):
        super(TestDebug, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        self.patchUtils(self.new_root)

    def test_debug_write(self, m_locale):
        m_locale.return_value = 'en_US.UTF-8'
        cfg = {
            'abc': '123',
            'c': '\u20a0',
            'debug': {
                'verbose': True,
                # Does not actually write here due to mocking...
                'output': '/var/log/cloud-init-debug.log',
            },
        }
        cc = get_cloud()
        cc_debug.handle('cc_debug', cfg, cc, LOG, [])
        contents = util.load_file('/var/log/cloud-init-debug.log')
        # Some basic sanity tests...
        self.assertNotEqual(0, len(contents))
        for k in cfg.keys():
            self.assertIn(k, contents)

    def test_debug_no_write(self, m_locale):
        m_locale.return_value = 'en_US.UTF-8'
        cfg = {
            'abc': '123',
            'debug': {
                'verbose': False,
                # Does not actually write here due to mocking...
                'output': '/var/log/cloud-init-debug.log',
            },
        }
        cc = get_cloud()
        cc_debug.handle('cc_debug', cfg, cc, LOG, [])
        self.assertRaises(IOError,
                          util.load_file, '/var/log/cloud-init-debug.log')

# vi: ts=4 expandtab
