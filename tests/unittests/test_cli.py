import imp
import os
import six
import sys

from . import helpers as test_helpers
mock = test_helpers.mock

BIN_CLOUDINIT = "bin/cloud-init"


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
            'cli', open(BIN_CLOUDINIT), '', ('', 'r', imp.PY_SOURCE))
        try:
            return cli.main()
        except Exception:
            pass

    @test_helpers.skipIf(not os.path.isfile(BIN_CLOUDINIT), "no bin/cloudinit")
    def test_no_arguments_shows_usage(self):
        self._call_main()
        self.assertIn('usage: cloud-init', self.stderr.getvalue())

    @test_helpers.skipIf(not os.path.isfile(BIN_CLOUDINIT), "no bin/cloudinit")
    def test_no_arguments_exits_2(self):
        exit_code = self._call_main()
        if self.sys_exit.call_count:
            self.assertEqual(mock.call(2), self.sys_exit.call_args)
        else:
            self.assertEqual(2, exit_code)

    @test_helpers.skipIf(not os.path.isfile(BIN_CLOUDINIT), "no bin/cloudinit")
    def test_no_arguments_shows_error_message(self):
        self._call_main()
        self.assertIn('cloud-init: error: too few arguments',
                      self.stderr.getvalue())
