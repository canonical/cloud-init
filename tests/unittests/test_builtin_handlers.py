"""Tests of the built-in user data handlers."""

import os
import unittest

from mocker import MockerTestCase

from cloudinit import handlers
from cloudinit import helpers
from cloudinit import util

from cloudinit.handlers import upstart_job

from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)


class TestBuiltins(MockerTestCase):

    def test_upstart_frequency_no_out(self):
        c_root = self.makeDir()
        up_root = self.makeDir()
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
        self.assertEquals(0, len(os.listdir(up_root)))

    @unittest.skip("until LP: #1124384 fixed")
    def test_upstart_frequency_single(self):
        # files should be written out when frequency is ! per-instance
        c_root = self.makeDir()
        up_root = self.makeDir()
        paths = helpers.Paths({
            'cloud_dir': c_root,
            'upstart_dir': up_root,
        })
        freq = PER_INSTANCE

        mock_subp = self.mocker.replace(util.subp, passthrough=False)
        mock_subp(["initctl", "reload-configuration"], capture=False)
        self.mocker.replay()

        h = upstart_job.UpstartJobPartHandler(paths)
        h.handle_part('', handlers.CONTENT_START,
                      None, None, None)
        h.handle_part('blah', 'text/upstart-job',
                      'test.conf', 'blah', freq)
        h.handle_part('', handlers.CONTENT_END,
                      None, None, None)
        self.assertEquals(1, len(os.listdir(up_root)))
