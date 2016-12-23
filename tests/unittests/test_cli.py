# This file is part of cloud-init. See LICENSE file for license information.

import six

from . import helpers as test_helpers

from cloudinit.cmd import main as cli

mock = test_helpers.mock


class TestCLI(test_helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestCLI, self).setUp()
        self.stderr = six.StringIO()
        self.patchStdoutAndStderr(stderr=self.stderr)

    def _call_main(self, sysv_args=None):
        if not sysv_args:
            sysv_args = ['cloud-init']
        try:
            return cli.main(sysv_args=sysv_args)
        except SystemExit as e:
            return e.code

    def test_no_arguments_shows_usage(self):
        exit_code = self._call_main()
        self.assertIn('usage: cloud-init', self.stderr.getvalue())
        self.assertEqual(2, exit_code)

    def test_no_arguments_shows_error_message(self):
        exit_code = self._call_main()
        self.assertIn('cloud-init: error: too few arguments',
                      self.stderr.getvalue())
        self.assertEqual(2, exit_code)


# vi: ts=4 expandtab
