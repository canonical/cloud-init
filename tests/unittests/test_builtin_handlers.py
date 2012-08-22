"""Tests of the built-in user data handlers."""

import os

from mocker import MockerTestCase

from cloudinit import handlers
from cloudinit import helpers

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

    def test_upstart_frequency_single(self):
        c_root = self.makeDir()
        up_root = self.makeDir()
        paths = helpers.Paths({
            'cloud_dir': c_root,
            'upstart_dir': up_root,
        })
        freq = PER_INSTANCE
        h = upstart_job.UpstartJobPartHandler(paths)
        # No files should be written out when
        # the frequency is ! per-instance
        h.handle_part('', handlers.CONTENT_START,
                      None, None, None)
        h.handle_part('blah', 'text/upstart-job',
                      'test.conf', 'blah', freq)
        h.handle_part('', handlers.CONTENT_END,
                      None, None, None)
        self.assertEquals(1, len(os.listdir(up_root)))
