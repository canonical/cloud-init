# This file is part of cloud-init. See LICENSE file for license information.

from six import StringIO
import os

from collections import namedtuple
from cloudinit.cmd.devel import render
from cloudinit.helpers import Paths
from cloudinit.sources import INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE
from cloudinit.tests.helpers import CiTestCase, mock, skipUnlessJinja
from cloudinit.util import ensure_dir, write_file


class TestRender(CiTestCase):

    with_logs = True

    args = namedtuple('renderargs', 'user_data instance_data debug')

    def setUp(self):
        super(TestRender, self).setUp()
        self.tmp = self.tmp_dir()

    def test_handle_args_error_on_missing_user_data(self):
        """When user_data file path does not exist, log an error."""
        absent_file = self.tmp_path('user-data', dir=self.tmp)
        instance_data = self.tmp_path('instance-data', dir=self.tmp)
        write_file(instance_data, '{}')
        args = self.args(
            user_data=absent_file, instance_data=instance_data, debug=False)
        with mock.patch('sys.stderr', new_callable=StringIO):
            self.assertEqual(1, render.handle_args('anyname', args))
        self.assertIn(
            'Missing user-data file: %s' % absent_file,
            self.logs.getvalue())

    def test_handle_args_error_on_missing_instance_data(self):
        """When instance_data file path does not exist, log an error."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        absent_file = self.tmp_path('instance-data', dir=self.tmp)
        args = self.args(
            user_data=user_data, instance_data=absent_file, debug=False)
        with mock.patch('sys.stderr', new_callable=StringIO):
            self.assertEqual(1, render.handle_args('anyname', args))
        self.assertIn(
            'Missing instance-data.json file: %s' % absent_file,
            self.logs.getvalue())

    def test_handle_args_defaults_instance_data(self):
        """When no instance_data argument, default to configured run_dir."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.devel.render.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        args = self.args(
            user_data=user_data, instance_data=None, debug=False)
        with mock.patch('sys.stderr', new_callable=StringIO):
            self.assertEqual(1, render.handle_args('anyname', args))
        json_file = os.path.join(run_dir, INSTANCE_JSON_FILE)
        self.assertIn(
            'Missing instance-data.json file: %s' % json_file,
            self.logs.getvalue())

    def test_handle_args_root_fallback_from_sensitive_instance_data(self):
        """When root user defaults to sensitive.json."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.devel.render.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        args = self.args(
            user_data=user_data, instance_data=None, debug=False)
        with mock.patch('sys.stderr', new_callable=StringIO):
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                self.assertEqual(1, render.handle_args('anyname', args))
        json_file = os.path.join(run_dir, INSTANCE_JSON_FILE)
        json_sensitive = os.path.join(run_dir, INSTANCE_JSON_SENSITIVE_FILE)
        self.assertIn(
            'WARNING: Missing root-readable %s. Using redacted %s' % (
                json_sensitive, json_file), self.logs.getvalue())
        self.assertIn(
            'ERROR: Missing instance-data.json file: %s' % json_file,
            self.logs.getvalue())

    def test_handle_args_root_uses_sensitive_instance_data(self):
        """When root user, and no instance-data arg, use sensitive.json."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        write_file(user_data, '##template: jinja\nrendering: {{ my_var }}')
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        ensure_dir(run_dir)
        json_sensitive = os.path.join(run_dir, INSTANCE_JSON_SENSITIVE_FILE)
        write_file(json_sensitive, '{"my-var": "jinja worked"}')
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.devel.render.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        args = self.args(
            user_data=user_data, instance_data=None, debug=False)
        with mock.patch('sys.stderr', new_callable=StringIO):
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                with mock.patch('os.getuid') as m_getuid:
                    m_getuid.return_value = 0
                    self.assertEqual(0, render.handle_args('anyname', args))
        self.assertIn('rendering: jinja worked', m_stdout.getvalue())

    @skipUnlessJinja()
    def test_handle_args_renders_instance_data_vars_in_template(self):
        """If user_data file is a jinja template render instance-data vars."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        write_file(user_data, '##template: jinja\nrendering: {{ my_var }}')
        instance_data = self.tmp_path('instance-data', dir=self.tmp)
        write_file(instance_data, '{"my-var": "jinja worked"}')
        args = self.args(
            user_data=user_data, instance_data=instance_data, debug=True)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_console_err:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(0, render.handle_args('anyname', args))
        self.assertIn(
            'DEBUG: Converted jinja variables\n{', self.logs.getvalue())
        self.assertIn(
            'DEBUG: Converted jinja variables\n{', m_console_err.getvalue())
        self.assertEqual('rendering: jinja worked', m_stdout.getvalue())

    @skipUnlessJinja()
    def test_handle_args_warns_and_gives_up_on_invalid_jinja_operation(self):
        """If user_data file has invalid jinja operations log warnings."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        write_file(user_data, '##template: jinja\nrendering: {{ my-var }}')
        instance_data = self.tmp_path('instance-data', dir=self.tmp)
        write_file(instance_data, '{"my-var": "jinja worked"}')
        args = self.args(
            user_data=user_data, instance_data=instance_data, debug=True)
        with mock.patch('sys.stderr', new_callable=StringIO):
            self.assertEqual(1, render.handle_args('anyname', args))
        self.assertIn(
            'WARNING: Ignoring jinja template for %s: Undefined jinja'
            ' variable: "my-var". Jinja tried subtraction. Perhaps you meant'
            ' "my_var"?' % user_data,
            self.logs.getvalue())

# vi: ts=4 expandtab
