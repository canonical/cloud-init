# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.cmd import clean
from cloudinit.util import ensure_dir, sym_link, write_file
from cloudinit.tests.helpers import CiTestCase, wrap_and_call, mock
from collections import namedtuple
import os
from six import StringIO

mypaths = namedtuple('MyPaths', 'cloud_dir')


class TestClean(CiTestCase):

    def setUp(self):
        super(TestClean, self).setUp()
        self.new_root = self.tmp_dir()
        self.artifact_dir = self.tmp_path('artifacts', self.new_root)
        self.log1 = self.tmp_path('cloud-init.log', self.new_root)
        self.log2 = self.tmp_path('cloud-init-output.log', self.new_root)

        class FakeInit(object):
            cfg = {'def_log_file': self.log1,
                   'output': {'all': '|tee -a {0}'.format(self.log2)}}
            paths = mypaths(cloud_dir=self.artifact_dir)

            def __init__(self, ds_deps):
                pass

            def read_cfg(self):
                pass

        self.init_class = FakeInit

    def test_remove_artifacts_removes_logs(self):
        """remove_artifacts removes logs when remove_logs is True."""
        write_file(self.log1, 'cloud-init-log')
        write_file(self.log2, 'cloud-init-output-log')

        self.assertFalse(
            os.path.exists(self.artifact_dir), 'Unexpected artifacts dir')
        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'Init': {'side_effect': self.init_class}},
            clean.remove_artifacts, remove_logs=True)
        self.assertFalse(os.path.exists(self.log1), 'Unexpected file')
        self.assertFalse(os.path.exists(self.log2), 'Unexpected file')
        self.assertEqual(0, retcode)

    def test_remove_artifacts_preserves_logs(self):
        """remove_artifacts leaves logs when remove_logs is False."""
        write_file(self.log1, 'cloud-init-log')
        write_file(self.log2, 'cloud-init-output-log')

        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'Init': {'side_effect': self.init_class}},
            clean.remove_artifacts, remove_logs=False)
        self.assertTrue(os.path.exists(self.log1), 'Missing expected file')
        self.assertTrue(os.path.exists(self.log2), 'Missing expected file')
        self.assertEqual(0, retcode)

    def test_remove_artifacts_removes_unlinks_symlinks(self):
        """remove_artifacts cleans artifacts dir unlinking any symlinks."""
        dir1 = os.path.join(self.artifact_dir, 'dir1')
        ensure_dir(dir1)
        symlink = os.path.join(self.artifact_dir, 'mylink')
        sym_link(dir1, symlink)

        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'Init': {'side_effect': self.init_class}},
            clean.remove_artifacts, remove_logs=False)
        self.assertEqual(0, retcode)
        for path in (dir1, symlink):
            self.assertFalse(
                os.path.exists(path),
                'Unexpected {0} dir'.format(path))

    def test_remove_artifacts_removes_artifacts_skipping_seed(self):
        """remove_artifacts cleans artifacts dir with exception of seed dir."""
        dirs = [
            self.artifact_dir,
            os.path.join(self.artifact_dir, 'seed'),
            os.path.join(self.artifact_dir, 'dir1'),
            os.path.join(self.artifact_dir, 'dir2')]
        for _dir in dirs:
            ensure_dir(_dir)

        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'Init': {'side_effect': self.init_class}},
            clean.remove_artifacts, remove_logs=False)
        self.assertEqual(0, retcode)
        for expected_dir in dirs[:2]:
            self.assertTrue(
                os.path.exists(expected_dir),
                'Missing {0} dir'.format(expected_dir))
        for deleted_dir in dirs[2:]:
            self.assertFalse(
                os.path.exists(deleted_dir),
                'Unexpected {0} dir'.format(deleted_dir))

    def test_remove_artifacts_removes_artifacts_removes_seed(self):
        """remove_artifacts removes seed dir when remove_seed is True."""
        dirs = [
            self.artifact_dir,
            os.path.join(self.artifact_dir, 'seed'),
            os.path.join(self.artifact_dir, 'dir1'),
            os.path.join(self.artifact_dir, 'dir2')]
        for _dir in dirs:
            ensure_dir(_dir)

        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'Init': {'side_effect': self.init_class}},
            clean.remove_artifacts, remove_logs=False, remove_seed=True)
        self.assertEqual(0, retcode)
        self.assertTrue(
            os.path.exists(self.artifact_dir), 'Missing artifact dir')
        for deleted_dir in dirs[1:]:
            self.assertFalse(
                os.path.exists(deleted_dir),
                'Unexpected {0} dir'.format(deleted_dir))

    def test_remove_artifacts_returns_one_on_errors(self):
        """remove_artifacts returns non-zero on failure and prints an error."""
        ensure_dir(self.artifact_dir)
        ensure_dir(os.path.join(self.artifact_dir, 'dir1'))

        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            retcode = wrap_and_call(
                'cloudinit.cmd.clean',
                {'del_dir': {'side_effect': OSError('oops')},
                 'Init': {'side_effect': self.init_class}},
                clean.remove_artifacts, remove_logs=False)
        self.assertEqual(1, retcode)
        self.assertEqual(
            'ERROR: Could not remove dir1: oops\n', m_stderr.getvalue())

    def test_handle_clean_args_reboots(self):
        """handle_clean_args_reboots when reboot arg is provided."""

        called_cmds = []

        def fake_subp(cmd, capture):
            called_cmds.append((cmd, capture))
            return '', ''

        myargs = namedtuple('MyArgs', 'remove_logs remove_seed reboot')
        cmdargs = myargs(remove_logs=False, remove_seed=False, reboot=True)
        retcode = wrap_and_call(
            'cloudinit.cmd.clean',
            {'subp': {'side_effect': fake_subp},
             'Init': {'side_effect': self.init_class}},
            clean.handle_clean_args, name='does not matter', args=cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual(
            [(['shutdown', '-r', 'now'], False)], called_cmds)

    def test_status_main(self):
        '''clean.main can be run as a standalone script.'''
        write_file(self.log1, 'cloud-init-log')
        with self.assertRaises(SystemExit) as context_manager:
            wrap_and_call(
                'cloudinit.cmd.clean',
                {'Init': {'side_effect': self.init_class},
                 'sys.exit': {'side_effect': self.sys_exit},
                 'sys.argv': {'new': ['clean', '--logs']}},
                clean.main)

        self.assertEqual(0, context_manager.exception.code)
        self.assertFalse(
            os.path.exists(self.log1), 'Unexpected log {0}'.format(self.log1))


# vi: ts=4 expandtab syntax=python
