# This file is part of cloud-init. See LICENSE file for license information.

import errno
from six import StringIO
from textwrap import dedent
import os

from collections import namedtuple
from cloudinit.cmd import query
from cloudinit.helpers import Paths
from cloudinit.sources import (
    REDACT_SENSITIVE_VALUE, INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE)
from cloudinit.tests.helpers import CiTestCase, mock
from cloudinit.util import ensure_dir, write_file


class TestQuery(CiTestCase):

    with_logs = True

    args = namedtuple(
        'queryargs',
        ('debug dump_all format instance_data list_keys user_data vendor_data'
         ' varname'))

    def setUp(self):
        super(TestQuery, self).setUp()
        self.tmp = self.tmp_dir()
        self.instance_data = self.tmp_path('instance-data', dir=self.tmp)

    def test_handle_args_error_on_missing_param(self):
        """Error when missing required parameters and print usage."""
        args = self.args(
            debug=False, dump_all=False, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(1, query.handle_args('anyname', args))
        expected_error = (
            'ERROR: Expected one of the options: --all, --format, --list-keys'
            ' or varname\n')
        self.assertIn(expected_error, self.logs.getvalue())
        self.assertIn('usage: query', m_stdout.getvalue())
        self.assertIn(expected_error, m_stderr.getvalue())

    def test_handle_args_error_on_missing_instance_data(self):
        """When instance_data file path does not exist, log an error."""
        absent_fn = self.tmp_path('absent', dir=self.tmp)
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=absent_fn,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            self.assertEqual(1, query.handle_args('anyname', args))
        self.assertIn(
            'ERROR: Missing instance-data file: %s' % absent_fn,
            self.logs.getvalue())
        self.assertIn(
            'ERROR: Missing instance-data file: %s' % absent_fn,
            m_stderr.getvalue())

    def test_handle_args_error_when_no_read_permission_instance_data(self):
        """When instance_data file is unreadable, log an error."""
        noread_fn = self.tmp_path('unreadable', dir=self.tmp)
        write_file(noread_fn, 'thou shall not pass')
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=noread_fn,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('cloudinit.cmd.query.util.load_file') as m_load:
                m_load.side_effect = OSError(errno.EACCES, 'Not allowed')
                self.assertEqual(1, query.handle_args('anyname', args))
        self.assertIn(
            "ERROR: No read permission on '%s'. Try sudo" % noread_fn,
            self.logs.getvalue())
        self.assertIn(
            "ERROR: No read permission on '%s'. Try sudo" % noread_fn,
            m_stderr.getvalue())

    def test_handle_args_defaults_instance_data(self):
        """When no instance_data argument, default to configured run_dir."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.query.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            self.assertEqual(1, query.handle_args('anyname', args))
        json_file = os.path.join(run_dir, INSTANCE_JSON_FILE)
        self.assertIn(
            'ERROR: Missing instance-data file: %s' % json_file,
            self.logs.getvalue())
        self.assertIn(
            'ERROR: Missing instance-data file: %s' % json_file,
            m_stderr.getvalue())

    def test_handle_args_root_fallsback_to_instance_data(self):
        """When no instance_data argument, root falls back to redacted json."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.query.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                self.assertEqual(1, query.handle_args('anyname', args))
        json_file = os.path.join(run_dir, INSTANCE_JSON_FILE)
        sensitive_file = os.path.join(run_dir, INSTANCE_JSON_SENSITIVE_FILE)
        self.assertIn(
            'WARNING: Missing root-readable %s. Using redacted %s instead.' % (
                sensitive_file, json_file),
            m_stderr.getvalue())

    def test_handle_args_root_uses_instance_sensitive_data(self):
        """When no instance_data argument, root uses semsitive json."""
        user_data = self.tmp_path('user-data', dir=self.tmp)
        vendor_data = self.tmp_path('vendor-data', dir=self.tmp)
        write_file(user_data, 'ud')
        write_file(vendor_data, 'vd')
        run_dir = self.tmp_path('run_dir', dir=self.tmp)
        sensitive_file = os.path.join(run_dir, INSTANCE_JSON_SENSITIVE_FILE)
        write_file(sensitive_file, '{"my-var": "it worked"}')
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        self.add_patch('cloudinit.cmd.query.read_cfg_paths', 'm_paths')
        self.m_paths.return_value = paths
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=vendor_data, vendor_data=vendor_data,
            varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual(
            '{\n "my_var": "it worked",\n "userdata": "vd",\n '
            '"vendordata": "vd"\n}\n', m_stdout.getvalue())

    def test_handle_args_dumps_all_instance_data(self):
        """When --all is specified query will dump all instance data vars."""
        write_file(self.instance_data, '{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=self.instance_data, list_keys=False,
            user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual(
            '{\n "my_var": "it worked",\n "userdata": "<%s> file:ud",\n'
            ' "vendordata": "<%s> file:vd"\n}\n' % (
                REDACT_SENSITIVE_VALUE, REDACT_SENSITIVE_VALUE),
            m_stdout.getvalue())

    def test_handle_args_returns_top_level_varname(self):
        """When the argument varname is passed, report its value."""
        write_file(self.instance_data, '{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=self.instance_data, list_keys=False,
            user_data='ud', vendor_data='vd', varname='my_var')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual('it worked\n', m_stdout.getvalue())

    def test_handle_args_returns_nested_varname(self):
        """If user_data file is a jinja template render instance-data vars."""
        write_file(self.instance_data,
                   '{"v1": {"key-2": "value-2"}, "my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=self.instance_data, user_data='ud', vendor_data='vd',
            list_keys=False, varname='v1.key_2')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual('value-2\n', m_stdout.getvalue())

    def test_handle_args_returns_standardized_vars_to_top_level_aliases(self):
        """Any standardized vars under v# are promoted as top-level aliases."""
        write_file(
            self.instance_data,
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}')
        expected = dedent("""\
            {
             "top": "gun",
             "userdata": "<redacted for non-root user> file:ud",
             "v1": {
              "v1_1": "val1.1"
             },
             "v1_1": "val1.1",
             "v2": {
              "v2_2": "val2.2"
             },
             "v2_2": "val2.2",
             "vendordata": "<redacted for non-root user> file:vd"
            }
        """)
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=self.instance_data, user_data='ud', vendor_data='vd',
            list_keys=False, varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual(expected, m_stdout.getvalue())

    def test_handle_args_list_keys_sorts_top_level_keys_when_no_varname(self):
        """Sort all top-level keys when only --list-keys provided."""
        write_file(
            self.instance_data,
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}')
        expected = 'top\nuserdata\nv1\nv1_1\nv2\nv2_2\nvendordata\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=self.instance_data, list_keys=True, user_data='ud',
            vendor_data='vd', varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual(expected, m_stdout.getvalue())

    def test_handle_args_list_keys_sorts_nested_keys_when_varname(self):
        """Sort all nested keys of varname object when --list-keys provided."""
        write_file(
            self.instance_data,
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2":' +
            ' {"v2_2": "val2.2"}, "top": "gun"}')
        expected = 'v1_1\nv1_2\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=self.instance_data, list_keys=True,
            user_data='ud', vendor_data='vd', varname='v1')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            self.assertEqual(0, query.handle_args('anyname', args))
        self.assertEqual(expected, m_stdout.getvalue())

    def test_handle_args_list_keys_errors_when_varname_is_not_a_dict(self):
        """Raise an error when --list-keys and varname specify a non-list."""
        write_file(
            self.instance_data,
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": ' +
            '{"v2_2": "val2.2"}, "top": "gun"}')
        expected_error = "ERROR: --list-keys provided but 'top' is not a dict"
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=self.instance_data, list_keys=True, user_data='ud',
            vendor_data='vd',  varname='top')
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(1, query.handle_args('anyname', args))
        self.assertEqual('', m_stdout.getvalue())
        self.assertIn(expected_error, m_stderr.getvalue())

# vi: ts=4 expandtab
