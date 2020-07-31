# This file is part of cloud-init. See LICENSE file for license inforselfmation.

import errno
from io import StringIO
from textwrap import dedent
import os

import pytest

from collections import namedtuple
from cloudinit.cmd import query
from cloudinit.helpers import Paths
from cloudinit.sources import (
    REDACT_SENSITIVE_VALUE, INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE)
from cloudinit.tests.helpers import mock
from cloudinit.util import ensure_dir


class TestQuery:

    args = namedtuple(
        'queryargs',
        ('debug dump_all format instance_data list_keys user_data vendor_data'
         ' varname'))

    def test_handle_args_error_on_missing_param(self, caplog):
        """Error when missing required parameters and print usage."""
        args = self.args(
            debug=False, dump_all=False, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                assert 1 == query.handle_args('anyname', args)
        expected_error = (
            'Expected one of the options: --all, --format, --list-keys'
            ' or varname\n')
        logs = caplog.text
        assert expected_error in logs
        assert 'usage: query' in m_stdout.getvalue()
        assert expected_error in m_stderr.getvalue()

    def test_handle_args_error_on_missing_instance_data(self, tmpdir, caplog):
        """When instance_data file path does not exist, log an error."""
        absent_fn = tmpdir.join('absent')
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=absent_fn,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            assert 1 == query.handle_args('anyname', args)

        msg = 'Missing instance-data file: %s' % absent_fn
        assert msg in caplog.text
        assert msg in m_stderr.getvalue()

    def test_handle_args_error_when_no_read_permission_instance_data(
        self, tmpdir, caplog
    ):
        """When instance_data file is unreadable, log an error."""
        noread_fn = tmpdir.join('unreadable')
        noread_fn.write('thou shall not pass')
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=noread_fn,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('cloudinit.cmd.query.util.load_file') as m_load:
                m_load.side_effect = OSError(errno.EACCES, 'Not allowed')
                assert 1 == query.handle_args('anyname', args)
        msg = "No read permission on '%s'. Try sudo" % noread_fn
        assert msg in caplog.text
        assert msg in m_stderr.getvalue()

    def test_handle_args_defaults_instance_data(self, tmpdir, caplog):
        """When no instance_data argument, default to configured run_dir."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = tmpdir.join('run_dir')
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
                m_paths.return_value = paths
                assert 1 == query.handle_args('anyname', args)
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        msg = 'Missing instance-data file: %s' % json_file.strpath
        assert msg in caplog.text
        assert msg in m_stderr.getvalue()

    def test_handle_args_root_fallsback_to_instance_data(self, tmpdir):
        """When no instance_data argument, root falls back to redacted json."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = tmpdir.join('run_dir')
        ensure_dir(run_dir)
        paths = Paths({'run_dir': run_dir})
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
                m_paths.return_value = paths
                with mock.patch('os.getuid') as m_getuid:
                    m_getuid.return_value = 0
                    assert 1 == query.handle_args('anyname', args)
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        sensitive_file = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        msg = (
            'WARNING: Missing root-readable %s. Using redacted %s instead.' % (
                sensitive_file.strpath, json_file.strpath
            )
        )
        assert msg in m_stderr.getvalue()

    def test_handle_args_root_uses_instance_sensitive_data(self, tmpdir):
        """When no instance_data argument, root uses sensitive json."""
        user_data = tmpdir.join('user-data')
        vendor_data = tmpdir.join('vendor-data')
        user_data.write('ud')
        vendor_data.write('vd')
        run_dir = tmpdir.join('run_dir')
        sensitive_file = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        ensure_dir(run_dir)
        sensitive_file.write('{"my-var": "it worked"}')
        paths = Paths({'run_dir': run_dir})
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=user_data, vendor_data=vendor_data,
            varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
                m_paths.return_value = paths
                with mock.patch('os.getuid') as m_getuid:
                    m_getuid.return_value = 0
                    assert 0 == query.handle_args('anyname', args)
        expected = (
            '{\n "my_var": "it worked",\n "userdata": "ud",\n '
            '"vendordata": "vd"\n}\n'
        )
        assert expected == m_stdout.getvalue()

    def test_handle_args_dumps_all_instance_data(self, tmpdir):
        """When --all is specified query will dump all instance data vars."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write('{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=instance_data, list_keys=False,
            user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        expected = (
            '{\n "my_var": "it worked",\n "userdata": "<%s> file:ud",\n'
            ' "vendordata": "<%s> file:vd"\n}\n' % (
                REDACT_SENSITIVE_VALUE, REDACT_SENSITIVE_VALUE
            )
        )
        assert expected == m_stdout.getvalue()

    def test_handle_args_returns_top_level_varname(self, tmpdir):
        """When the argument varname is passed, report its value."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write('{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=instance_data, list_keys=False,
            user_data='ud', vendor_data='vd', varname='my_var')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        assert 'it worked\n' == m_stdout.getvalue()

    def test_handle_args_returns_nested_varname(self, tmpdir):
        """If user_data file is a jinja template render instance-data vars."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"key-2": "value-2"}, "my-var": "it worked"}'
        )
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data, user_data='ud', vendor_data='vd',
            list_keys=False, varname='v1.key_2')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        assert 'value-2\n' == m_stdout.getvalue()

    def test_handle_args_returns_standardized_vars_to_top_level_aliases(
        self, tmpdir
    ):
        """Any standardized vars under v# are promoted as top-level aliases."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
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
            instance_data=instance_data, user_data='ud', vendor_data='vd',
            list_keys=False, varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        assert expected == m_stdout.getvalue()

    def test_handle_args_list_keys_sorts_top_level_keys_when_no_varname(
        self, tmpdir
    ):
        """Sort all top-level keys when only --list-keys provided."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}')
        expected = 'top\nuserdata\nv1\nv1_1\nv2\nv2_2\nvendordata\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data, list_keys=True, user_data='ud',
            vendor_data='vd', varname=None)
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        assert expected == m_stdout.getvalue()

    def test_handle_args_list_keys_sorts_nested_keys_when_varname(
        self, tmpdir
    ):
        """Sort all nested keys of varname object when --list-keys provided."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2":' +
            ' {"v2_2": "val2.2"}, "top": "gun"}')
        expected = 'v1_1\nv1_2\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data, list_keys=True,
            user_data='ud', vendor_data='vd', varname='v1')
        with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 100
                assert 0 == query.handle_args('anyname', args)
        assert expected == m_stdout.getvalue()

    def test_handle_args_list_keys_errors_when_varname_is_not_a_dict(
        self, tmpdir
    ):
        """Raise an error when --list-keys and varname specify a non-list."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": ' +
            '{"v2_2": "val2.2"}, "top": "gun"}')
        expected_error = "--list-keys provided but 'top' is not a dict"
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data, list_keys=True, user_data='ud',
            vendor_data='vd', varname='top')
        with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                with mock.patch('os.getuid') as m_getuid:
                    m_getuid.return_value = 100
                    assert 1 == query.handle_args('anyname', args)
        assert '' == m_stdout.getvalue()
        assert expected_error in m_stderr.getvalue()

# vi: ts=4 expandtab
