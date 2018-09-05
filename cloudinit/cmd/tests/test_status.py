# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
import os
from six import StringIO
from textwrap import dedent

from cloudinit.atomic_helper import write_json
from cloudinit.cmd import status
from cloudinit.util import ensure_file
from cloudinit.tests.helpers import CiTestCase, wrap_and_call, mock

mypaths = namedtuple('MyPaths', 'run_dir')
myargs = namedtuple('MyArgs', 'long wait')


class TestStatus(CiTestCase):

    def setUp(self):
        super(TestStatus, self).setUp()
        self.new_root = self.tmp_dir()
        self.status_file = self.tmp_path('status.json', self.new_root)
        self.disable_file = self.tmp_path('cloudinit-disable', self.new_root)
        self.paths = mypaths(run_dir=self.new_root)

        class FakeInit(object):
            paths = self.paths

            def __init__(self, ds_deps):
                pass

            def read_cfg(self):
                pass

        self.init_class = FakeInit

    def test__is_cloudinit_disabled_false_on_sysvinit(self):
        '''When not in an environment using systemd, return False.'''
        ensure_file(self.disable_file)  # Create the ignored disable file
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': False,
             'get_cmdline': "root=/dev/my-root not-important"},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertFalse(
            is_disabled, 'expected enabled cloud-init on sysvinit')
        self.assertEqual('Cloud-init enabled on sysvinit', reason)

    def test__is_cloudinit_disabled_true_on_disable_file(self):
        '''When using systemd and disable_file is present return disabled.'''
        ensure_file(self.disable_file)  # Create observed disable file
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': True,
             'get_cmdline': "root=/dev/my-root not-important"},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertTrue(is_disabled, 'expected disabled cloud-init')
        self.assertEqual(
            'Cloud-init disabled by {0}'.format(self.disable_file), reason)

    def test__is_cloudinit_disabled_false_on_kernel_cmdline_enable(self):
        '''Not disabled when using systemd and enabled via commandline.'''
        ensure_file(self.disable_file)  # Create ignored disable file
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': True,
             'get_cmdline': 'something cloud-init=enabled else'},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertFalse(is_disabled, 'expected enabled cloud-init')
        self.assertEqual(
            'Cloud-init enabled by kernel command line cloud-init=enabled',
            reason)

    def test__is_cloudinit_disabled_true_on_kernel_cmdline(self):
        '''When using systemd and disable_file is present return disabled.'''
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': True,
             'get_cmdline': 'something cloud-init=disabled else'},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertTrue(is_disabled, 'expected disabled cloud-init')
        self.assertEqual(
            'Cloud-init disabled by kernel parameter cloud-init=disabled',
            reason)

    def test__is_cloudinit_disabled_true_when_generator_disables(self):
        '''When cloud-init-generator doesn't write enabled file return True.'''
        enabled_file = os.path.join(self.paths.run_dir, 'enabled')
        self.assertFalse(os.path.exists(enabled_file))
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': True,
             'get_cmdline': 'something'},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertTrue(is_disabled, 'expected disabled cloud-init')
        self.assertEqual('Cloud-init disabled by cloud-init-generator', reason)

    def test__is_cloudinit_disabled_false_when_enabled_in_systemd(self):
        '''Report enabled when systemd generator creates the enabled file.'''
        enabled_file = os.path.join(self.paths.run_dir, 'enabled')
        ensure_file(enabled_file)
        (is_disabled, reason) = wrap_and_call(
            'cloudinit.cmd.status',
            {'uses_systemd': True,
             'get_cmdline': 'something ignored'},
            status._is_cloudinit_disabled, self.disable_file, self.paths)
        self.assertFalse(is_disabled, 'expected enabled cloud-init')
        self.assertEqual(
            'Cloud-init enabled by systemd cloud-init-generator', reason)

    def test_status_returns_not_run(self):
        '''When status.json does not exist yet, return 'not run'.'''
        self.assertFalse(
            os.path.exists(self.status_file), 'Unexpected status.json found')
        cmdargs = myargs(long=False, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual('status: not run\n', m_stdout.getvalue())

    def test_status_returns_disabled_long_on_presence_of_disable_file(self):
        '''When cloudinit is disabled, return disabled reason.'''

        checked_files = []

        def fakeexists(filepath):
            checked_files.append(filepath)
            status_file = os.path.join(self.paths.run_dir, 'status.json')
            return bool(not filepath == status_file)

        cmdargs = myargs(long=True, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'os.path.exists': {'side_effect': fakeexists},
                 '_is_cloudinit_disabled': (True, 'disabled for some reason'),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual(
            [os.path.join(self.paths.run_dir, 'status.json')],
            checked_files)
        expected = dedent('''\
            status: disabled
            detail:
            disabled for some reason
        ''')
        self.assertEqual(expected, m_stdout.getvalue())

    def test_status_returns_running_on_no_results_json(self):
        '''Report running when status.json exists but result.json does not.'''
        result_file = self.tmp_path('result.json', self.new_root)
        write_json(self.status_file, {})
        self.assertFalse(
            os.path.exists(result_file), 'Unexpected result.json found')
        cmdargs = myargs(long=False, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual('status: running\n', m_stdout.getvalue())

    def test_status_returns_running(self):
        '''Report running when status exists with an unfinished stage.'''
        ensure_file(self.tmp_path('result.json', self.new_root))
        write_json(self.status_file,
                   {'v1': {'init': {'start': 1, 'finished': None}}})
        cmdargs = myargs(long=False, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual('status: running\n', m_stdout.getvalue())

    def test_status_returns_done(self):
        '''Report done results.json exists no stages are unfinished.'''
        ensure_file(self.tmp_path('result.json', self.new_root))
        write_json(
            self.status_file,
            {'v1': {'stage': None,  # No current stage running
                    'datasource': (
                        'DataSourceNoCloud [seed=/var/.../seed/nocloud-net]'
                        '[dsmode=net]'),
                    'blah': {'finished': 123.456},
                    'init': {'errors': [], 'start': 124.567,
                             'finished': 125.678},
                    'init-local': {'start': 123.45, 'finished': 123.46}}})
        cmdargs = myargs(long=False, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual('status: done\n', m_stdout.getvalue())

    def test_status_returns_done_long(self):
        '''Long format of done status includes datasource info.'''
        ensure_file(self.tmp_path('result.json', self.new_root))
        write_json(
            self.status_file,
            {'v1': {'stage': None,
                    'datasource': (
                        'DataSourceNoCloud [seed=/var/.../seed/nocloud-net]'
                        '[dsmode=net]'),
                    'init': {'start': 124.567, 'finished': 125.678},
                    'init-local': {'start': 123.45, 'finished': 123.46}}})
        cmdargs = myargs(long=True, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        expected = dedent('''\
            status: done
            time: Thu, 01 Jan 1970 00:02:05 +0000
            detail:
            DataSourceNoCloud [seed=/var/.../seed/nocloud-net][dsmode=net]
        ''')
        self.assertEqual(expected, m_stdout.getvalue())

    def test_status_on_errors(self):
        '''Reports error when any stage has errors.'''
        write_json(
            self.status_file,
            {'v1': {'stage': None,
                    'blah': {'errors': [], 'finished': 123.456},
                    'init': {'errors': ['error1'], 'start': 124.567,
                             'finished': 125.678},
                    'init-local': {'start': 123.45, 'finished': 123.46}}})
        cmdargs = myargs(long=False, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(1, retcode)
        self.assertEqual('status: error\n', m_stdout.getvalue())

    def test_status_on_errors_long(self):
        '''Long format of error status includes all error messages.'''
        write_json(
            self.status_file,
            {'v1': {'stage': None,
                    'datasource': (
                        'DataSourceNoCloud [seed=/var/.../seed/nocloud-net]'
                        '[dsmode=net]'),
                    'init': {'errors': ['error1'], 'start': 124.567,
                             'finished': 125.678},
                    'init-local': {'errors': ['error2', 'error3'],
                                   'start': 123.45, 'finished': 123.46}}})
        cmdargs = myargs(long=True, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(1, retcode)
        expected = dedent('''\
            status: error
            time: Thu, 01 Jan 1970 00:02:05 +0000
            detail:
            error1
            error2
            error3
        ''')
        self.assertEqual(expected, m_stdout.getvalue())

    def test_status_returns_running_long_format(self):
        '''Long format reports the stage in which we are running.'''
        write_json(
            self.status_file,
            {'v1': {'stage': 'init',
                    'init': {'start': 124.456, 'finished': None},
                    'init-local': {'start': 123.45, 'finished': 123.46}}})
        cmdargs = myargs(long=True, wait=False)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        expected = dedent('''\
            status: running
            time: Thu, 01 Jan 1970 00:02:04 +0000
            detail:
            Running in stage: init
        ''')
        self.assertEqual(expected, m_stdout.getvalue())

    def test_status_wait_blocks_until_done(self):
        '''Specifying wait will poll every 1/4 second until done state.'''
        running_json = {
            'v1': {'stage': 'init',
                   'init': {'start': 124.456, 'finished': None},
                   'init-local': {'start': 123.45, 'finished': 123.46}}}
        done_json = {
            'v1': {'stage': None,
                   'init': {'start': 124.456, 'finished': 125.678},
                   'init-local': {'start': 123.45, 'finished': 123.46}}}

        self.sleep_calls = 0

        def fake_sleep(interval):
            self.assertEqual(0.25, interval)
            self.sleep_calls += 1
            if self.sleep_calls == 2:
                write_json(self.status_file, running_json)
            elif self.sleep_calls == 3:
                write_json(self.status_file, done_json)
                result_file = self.tmp_path('result.json', self.new_root)
                ensure_file(result_file)

        cmdargs = myargs(long=False, wait=True)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'sleep': {'side_effect': fake_sleep},
                 '_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(0, retcode)
        self.assertEqual(4, self.sleep_calls)
        self.assertEqual('....\nstatus: done\n', m_stdout.getvalue())

    def test_status_wait_blocks_until_error(self):
        '''Specifying wait will poll every 1/4 second until error state.'''
        running_json = {
            'v1': {'stage': 'init',
                   'init': {'start': 124.456, 'finished': None},
                   'init-local': {'start': 123.45, 'finished': 123.46}}}
        error_json = {
            'v1': {'stage': None,
                   'init': {'errors': ['error1'], 'start': 124.456,
                            'finished': 125.678},
                   'init-local': {'start': 123.45, 'finished': 123.46}}}

        self.sleep_calls = 0

        def fake_sleep(interval):
            self.assertEqual(0.25, interval)
            self.sleep_calls += 1
            if self.sleep_calls == 2:
                write_json(self.status_file, running_json)
            elif self.sleep_calls == 3:
                write_json(self.status_file, error_json)

        cmdargs = myargs(long=False, wait=True)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                'cloudinit.cmd.status',
                {'sleep': {'side_effect': fake_sleep},
                 '_is_cloudinit_disabled': (False, ''),
                 'Init': {'side_effect': self.init_class}},
                status.handle_status_args, 'ignored', cmdargs)
        self.assertEqual(1, retcode)
        self.assertEqual(4, self.sleep_calls)
        self.assertEqual('....\nstatus: error\n', m_stdout.getvalue())

    def test_status_main(self):
        '''status.main can be run as a standalone script.'''
        write_json(self.status_file,
                   {'v1': {'init': {'start': 1, 'finished': None}}})
        with self.assertRaises(SystemExit) as context_manager:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                wrap_and_call(
                    'cloudinit.cmd.status',
                    {'sys.argv': {'new': ['status']},
                     'sys.exit': {'side_effect': self.sys_exit},
                     '_is_cloudinit_disabled': (False, ''),
                     'Init': {'side_effect': self.init_class}},
                    status.main)
        self.assertEqual(0, context_manager.exception.code)
        self.assertEqual('status: running\n', m_stdout.getvalue())

# vi: ts=4 expandtab syntax=python
