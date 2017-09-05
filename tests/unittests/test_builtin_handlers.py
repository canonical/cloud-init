# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os
import shutil
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock

from cloudinit.tests import helpers as test_helpers

from cloudinit import handlers
from cloudinit import helpers
from cloudinit import util

from cloudinit.handlers import upstart_job

from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)


class TestBuiltins(test_helpers.FilesystemMockingTestCase):
    def test_upstart_frequency_no_out(self):
        c_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, c_root)
        up_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, up_root)
        paths = helpers.Paths({
            'cloud_dir': c_root,
            'upstart_dir': up_root,
        })
        freq = PER_ALWAYS
        h = upstart_job.UpstartJobPartHandler(paths)
        # No files should be written out when
        # the frequency is ! per-instance
        h.handle_part('', handlers.CONTENT_START,
                      None, None, None)
        h.handle_part('blah', 'text/upstart-job',
                      'test.conf', 'blah', freq)
        h.handle_part('', handlers.CONTENT_END,
                      None, None, None)
        self.assertEqual(0, len(os.listdir(up_root)))

    def test_upstart_frequency_single(self):
        # files should be written out when frequency is ! per-instance
        new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, new_root)
        freq = PER_INSTANCE

        self.patchOS(new_root)
        self.patchUtils(new_root)
        paths = helpers.Paths({
            'upstart_dir': "/etc/upstart",
        })

        upstart_job.SUITABLE_UPSTART = True
        util.ensure_dir("/run")
        util.ensure_dir("/etc/upstart")

        with mock.patch.object(util, 'subp') as mockobj:
            h = upstart_job.UpstartJobPartHandler(paths)
            h.handle_part('', handlers.CONTENT_START,
                          None, None, None)
            h.handle_part('blah', 'text/upstart-job',
                          'test.conf', 'blah', freq)
            h.handle_part('', handlers.CONTENT_END,
                          None, None, None)

            self.assertEqual(len(os.listdir('/etc/upstart')), 1)

        mockobj.assert_called_once_with(
            ['initctl', 'reload-configuration'], capture=False)

# vi: ts=4 expandtab
