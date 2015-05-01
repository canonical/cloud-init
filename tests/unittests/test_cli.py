import imp
import sys

import six

from . import helpers as test_helpers

try:
    from unittest import mock
except ImportError:
    import mock


class TestCLI(test_helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestCLI, self).setUp()
        self.stderr = six.StringIO()
        self.patchStdoutAndStderr(stderr=self.stderr)
        self.sys_exit = mock.MagicMock()
        self.patched_funcs.enter_context(
            mock.patch.object(sys, 'exit', self.sys_exit))

    def _call_main(self):
        self.patched_funcs.enter_context(
            mock.patch.object(sys, 'argv', ['cloud-init']))
        cli = imp.load_module(
            'cli', open('bin/cloud-init'), '', ('', 'r', imp.PY_SOURCE))
        try:
            return cli.main()
        except:
            pass

    def test_no_arguments_shows_usage(self):
        self._call_main()
        self.assertIn('usage: cloud-init', self.stderr.getvalue())

    def test_no_arguments_exits_2(self):
        exit_code = self._call_main()
        if self.sys_exit.call_count:
            self.assertEqual(mock.call(2), self.sys_exit.call_args)
        else:
            self.assertEqual(2, exit_code)

    def test_no_arguments_shows_error_message(self):
        self._call_main()
        self.assertIn('cloud-init: error: too few arguments',
                      self.stderr.getvalue())
