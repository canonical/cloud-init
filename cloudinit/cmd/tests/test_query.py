# This file is part of cloud-init. See LICENSE file for license information.

import errno
import gzip
from io import BytesIO
import json
from textwrap import dedent

import pytest

from collections import namedtuple
from cloudinit.cmd import query
from cloudinit.helpers import Paths
from cloudinit.sources import (
    REDACT_SENSITIVE_VALUE, INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE)
from cloudinit.tests.helpers import mock
from cloudinit.util import ensure_dir, write_file


def _gzip_data(data):
    with BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()


@mock.patch("cloudinit.cmd.query.addLogHandlerCLI", return_value="")
class TestQuery:

    args = namedtuple(
        'queryargs',
        ('debug dump_all format instance_data list_keys user_data vendor_data'
         ' varname'))

    def test_handle_args_error_on_missing_param(
        self, m_cli_log, caplog, capsys
    ):
        """Error when missing required parameters and print usage."""
        args = self.args(
            debug=False, dump_all=False, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        assert 1 == query.handle_args('anyname', args)
        expected_error = (
            'Expected one of the options: --all, --format, --list-keys'
            ' or varname\n')
        logs = caplog.text
        assert expected_error in logs
        out, _err = capsys.readouterr()
        assert 'usage: query' in out
        assert 1 == m_cli_log.call_count

    def test_handle_args_error_on_missing_instance_data(
        self, _m_cli_log, caplog, tmpdir
    ):
        """When instance_data file path does not exist, log an error."""
        absent_fn = tmpdir.join('absent')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=absent_fn.strpath,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        assert 1 == query.handle_args('anyname', args)

        msg = 'Missing instance-data file: %s' % absent_fn
        assert msg in caplog.text

    def test_handle_args_error_when_no_read_permission_instance_data(
        self, _m_log_cli, caplog, tmpdir
    ):
        """When instance_data file is unreadable, log an error."""
        noread_fn = tmpdir.join('unreadable')
        noread_fn.write('thou shall not pass')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=noread_fn.strpath,
            list_keys=False, user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('cloudinit.cmd.query.util.load_file') as m_load:
            m_load.side_effect = OSError(errno.EACCES, 'Not allowed')
            assert 1 == query.handle_args('anyname', args)
        msg = "No read permission on '%s'. Try sudo" % noread_fn
        assert msg in caplog.text

    def test_handle_args_defaults_instance_data(
        self, _m_log_cli, caplog, tmpdir
    ):
        """When no instance_data argument, default to configured run_dir."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = tmpdir.join('run_dir')
        ensure_dir(run_dir.strpath)
        paths = Paths({'run_dir': run_dir.strpath})
        with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
            m_paths.return_value = paths
            assert 1 == query.handle_args('anyname', args)
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        msg = 'Missing instance-data file: %s' % json_file.strpath
        assert msg in caplog.text

    def test_handle_args_root_fallsback_to_instance_data(
        self, _m_log_cli, caplog, tmpdir
    ):
        """When no instance_data argument, root falls back to redacted json."""
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=None, vendor_data=None, varname=None)
        run_dir = tmpdir.join('run_dir')
        ensure_dir(run_dir.strpath)
        paths = Paths({'run_dir': run_dir.strpath})
        with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
            m_paths.return_value = paths
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                assert 1 == query.handle_args('anyname', args)
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        sensitive_file = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        msg = (
            'Missing root-readable %s. Using redacted %s instead.' %
            (
                sensitive_file.strpath, json_file.strpath
            )
        )
        logs = caplog.text
        assert msg in logs

    @pytest.mark.parametrize(
        'ud_src,ud_expected,vd_src,vd_expected',
        (
            ('hi mom', 'hi mom', 'hi pops', 'hi pops'),
            ('ud'.encode('utf-8'), 'ud', 'vd'.encode('utf-8'), 'vd'),
            (_gzip_data(b'ud'), 'ud', _gzip_data(b'vd'), 'vd'),
            (_gzip_data('ud'.encode('utf-8')), 'ud', _gzip_data(b'vd'), 'vd'),
            (_gzip_data(b'ud') + b'invalid', 'ci-b64:',
             _gzip_data(b'vd') + b'invalid', 'ci-b64:'),
            # non-utf-8 encodable content
            ('hi mom'.encode('utf-16'), 'ci-b64:',
             'hi pops'.encode('utf-16'), 'ci-b64:'),
        )
    )
    def test_handle_args_root_processes_user_data(
        self, _m_log_cli, ud_src, ud_expected, vd_src, vd_expected, capsys,
        tmpdir
    ):
        """Support reading multiple user-data file content types"""
        user_data = tmpdir.join('user-data')
        vendor_data = tmpdir.join('vendor-data')
        write_file(user_data.strpath, ud_src)
        write_file(vendor_data.strpath, vd_src)
        run_dir = tmpdir.join('run_dir')
        sensitive_file = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        ensure_dir(run_dir.strpath)
        sensitive_file.write('{"my-var": "it worked"}')
        paths = Paths({'run_dir': run_dir.strpath})
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=user_data.strpath,
            vendor_data=vendor_data.strpath, varname=None)
        with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
            m_paths.return_value = paths
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        cmd_output = json.loads(out)
        assert cmd_output['my_var'] == "it worked"
        if ud_expected == 'ci-b64:':
            assert cmd_output['userdata'].startswith(ud_expected)
        else:
            assert cmd_output['userdata'] == ud_expected
        if vd_expected == 'ci-b64:':
            assert cmd_output['vendordata'].startswith(vd_expected)
        else:
            assert cmd_output['vendordata'] == vd_expected

    def test_handle_args_root_uses_instance_sensitive_data(
        self, _m_cli_log, capsys, tmpdir
    ):
        """When no instance_data argument, root uses sensitive json."""
        user_data = tmpdir.join('user-data')
        vendor_data = tmpdir.join('vendor-data')
        user_data.write('ud')
        vendor_data.write('vd')
        run_dir = tmpdir.join('run_dir')
        sensitive_file = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        ensure_dir(run_dir.strpath)
        sensitive_file.write('{"my-var": "it worked"}')
        paths = Paths({'run_dir': run_dir.strpath})
        args = self.args(
            debug=False, dump_all=True, format=None, instance_data=None,
            list_keys=False, user_data=user_data.strpath,
            vendor_data=vendor_data.strpath, varname=None)
        with mock.patch('cloudinit.cmd.query.read_cfg_paths') as m_paths:
            m_paths.return_value = paths
            with mock.patch('os.getuid') as m_getuid:
                m_getuid.return_value = 0
                assert 0 == query.handle_args('anyname', args)
        expected = (
            '{\n "my_var": "it worked",\n "userdata": "ud",\n '
            '"vendordata": "vd"\n}\n'
        )
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_dumps_all_instance_data(
        self, _m_cli_log, capsys, tmpdir
    ):
        """When --all is specified query will dump all instance data vars."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write('{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=instance_data.strpath, list_keys=False,
            user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        expected = (
            '{\n "my_var": "it worked",\n "userdata": "<%s> file:ud",\n'
            ' "vendordata": "<%s> file:vd"\n}\n' % (
                REDACT_SENSITIVE_VALUE, REDACT_SENSITIVE_VALUE
            )
        )
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_returns_top_level_varname(
        self, _m_cli_log, capsys, tmpdir
    ):
        """When the argument varname is passed, report its value."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write('{"my-var": "it worked"}')
        args = self.args(
            debug=False, dump_all=True, format=None,
            instance_data=instance_data.strpath, list_keys=False,
            user_data='ud', vendor_data='vd', varname='my_var')
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        assert 'it worked\n' == out

    def test_handle_args_returns_nested_varname(
        self, _m_cli_log, capsys, tmpdir
    ):
        """If user_data file is a jinja template render instance-data vars."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"key-2": "value-2"}, "my-var": "it worked"}'
        )
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data.strpath, user_data='ud',
            vendor_data='vd', list_keys=False, varname='v1.key_2')
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        assert 'value-2\n' == out

    def test_handle_args_returns_standardized_vars_to_top_level_aliases(
        self, _m_cli_log, capsys, tmpdir
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
            instance_data=instance_data.strpath, user_data='ud',
            vendor_data='vd', list_keys=False, varname=None)
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_sorts_top_level_keys_when_no_varname(
        self, _m_cli_log, capsys, tmpdir
    ):
        """Sort all top-level keys when only --list-keys provided."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}')
        expected = 'top\nuserdata\nv1\nv1_1\nv2\nv2_2\nvendordata\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data.strpath, list_keys=True,
            user_data='ud', vendor_data='vd', varname=None)
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_sorts_nested_keys_when_varname(
        self, _m_cli_log, capsys, tmpdir
    ):
        """Sort all nested keys of varname object when --list-keys provided."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2":' +
            ' {"v2_2": "val2.2"}, "top": "gun"}')
        expected = 'v1_1\nv1_2\n'
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data.strpath, list_keys=True,
            user_data='ud', vendor_data='vd', varname='v1')
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args('anyname', args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_errors_when_varname_is_not_a_dict(
        self, _m_cli_log, caplog, tmpdir
    ):
        """Raise an error when --list-keys and varname specify a non-list."""
        instance_data = tmpdir.join('instance-data')
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": ' +
            '{"v2_2": "val2.2"}, "top": "gun"}')
        expected_error = "--list-keys provided but 'top' is not a dict"
        args = self.args(
            debug=False, dump_all=False, format=None,
            instance_data=instance_data.strpath, list_keys=True,
            user_data='ud', vendor_data='vd', varname='top')
        with mock.patch('os.getuid') as m_getuid:
            m_getuid.return_value = 100
            assert 1 == query.handle_args('anyname', args)
        assert expected_error in caplog.text

# vi: ts=4 expandtab
