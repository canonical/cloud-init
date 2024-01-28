# This file is part of cloud-init. See LICENSE file for license information.

import errno
import gzip
import json
import os
from collections import namedtuple
from io import BytesIO
from pathlib import Path
from textwrap import dedent

import pytest

from cloudinit.atomic_helper import b64e
from cloudinit.cmd import query
from cloudinit.helpers import Paths
from cloudinit.sources import REDACT_SENSITIVE_VALUE
from cloudinit.templater import JinjaSyntaxParsingException
from cloudinit.util import write_file
from tests.unittests.helpers import mock

M_PATH = "cloudinit.cmd.query."


def _gzip_data(data):
    with BytesIO() as iobuf:
        with gzip.GzipFile(mode="wb", fileobj=iobuf, mtime=0) as gzfp:
            gzfp.write(data)
        return iobuf.getvalue()


@pytest.fixture(autouse=True)
def setup_mocks(mocker):
    mocker.patch("cloudinit.cmd.query.read_cfg_paths", return_value=Paths({}))


class TestQuery:
    Args = namedtuple(
        "Args",
        "debug dump_all format instance_data list_keys user_data vendor_data"
        " varname",
    )

    def _setup_paths(self, tmpdir, ud_val=None, vd_val=None):
        """Write userdata and vendordata into a tmpdir.

        Return:
            4-tuple : (paths, run_dir_path, userdata_path, vendordata_path)
        """
        if ud_val:
            user_data = tmpdir.join("user-data")
            write_file(user_data.strpath, ud_val)
        else:
            user_data = None
        if vd_val:
            vendor_data = tmpdir.join("vendor-data")
            write_file(vendor_data.strpath, vd_val)
        else:
            vendor_data = None
        run_dir = tmpdir.join("run_dir")
        run_dir.ensure_dir()

        cloud_dir = tmpdir.join("cloud_dir")
        cloud_dir.ensure_dir()

        return (
            Paths(
                {"cloud_dir": cloud_dir.strpath, "run_dir": run_dir.strpath}
            ),
            run_dir,
            user_data,
            vendor_data,
        )

    def test_handle_args_error_on_missing_param(self, caplog, capsys):
        """Error when missing required parameters and print usage."""
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=None,
        )
        assert 1 == query.handle_args("anyname", args)
        expected_error = (
            "Expected one of the options: --all, --format, --list-keys"
            " or varname\n"
        )
        assert expected_error in caplog.text
        out, _err = capsys.readouterr()
        assert "usage: query" in out

    @pytest.mark.parametrize(
        "inst_data,varname,expected_error",
        (
            (
                '{"v1": {"key-2": "value-2"}}',
                "v1.absent_leaf",
                "instance-data 'v1' has no 'absent_leaf'\n",
            ),
            (
                '{"v1": {"key-2": "value-2"}}',
                "absent_key",
                "Undefined instance-data key 'absent_key'\n",
            ),
        ),
    )
    def test_handle_args_error_on_invalid_varname_paths(
        self, inst_data, varname, expected_error, caplog, tmpdir
    ):
        """Error when varname is not a valid instance-data variable path."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(inst_data)
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=varname,
        )
        paths, _, _, _ = self._setup_paths(tmpdir)
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            with mock.patch(M_PATH + "load_userdata") as m_lud:
                m_lud.return_value = "ud"
                assert 1 == query.handle_args("anyname", args)
        assert expected_error in caplog.text

    def test_handle_args_error_on_missing_instance_data(self, caplog, tmpdir):
        """When instance_data file path does not exist, log an error."""
        absent_fn = tmpdir.join("absent")
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=absent_fn.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        assert 1 == query.handle_args("anyname", args)

        msg = "Missing instance-data file: %s" % absent_fn
        assert msg in caplog.text

    def test_handle_args_error_when_no_read_permission_instance_data(
        self, caplog, tmpdir
    ):
        """When instance_data file is unreadable, log an error."""
        noread_fn = tmpdir.join("unreadable")
        noread_fn.write("thou shall not pass")
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=noread_fn.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        with mock.patch(M_PATH + "util.load_file") as m_load:
            m_load.side_effect = OSError(errno.EACCES, "Not allowed")
            assert 1 == query.handle_args("anyname", args)
        msg = "No read permission on '%s'. Try sudo" % noread_fn
        assert msg in caplog.text

    @pytest.mark.parametrize(
        "exception",
        [
            (OSError(errno.EACCES, "Not allowed"),),
            (OSError(errno.ENOENT, "Not allowed"),),
            (IOError,),
        ],
    )
    def test_handle_args_error_when_no_read_permission_init_cfg(
        self, exception, capsys
    ):
        """query.handle_status_args exists with 1 and no sys-output."""
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=None,
        )
        with mock.patch(
            M_PATH + "read_cfg_paths",
            side_effect=exception,
        ) as m_read_cfg_paths:
            query.handle_args("anyname", args)
        assert m_read_cfg_paths.call_count == 1
        out, err = capsys.readouterr()
        assert not out
        assert not err

    def test_handle_args_defaults_instance_data(self, caplog, tmpdir):
        """When no instance_data argument, default to configured run_dir."""
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=None,
        )
        paths, _, _, _ = self._setup_paths(tmpdir)
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            assert 1 == query.handle_args("anyname", args)
        json_file = paths.get_runpath("instance_data")
        msg = f"Missing instance-data file: {json_file}"
        assert msg in caplog.text

    def test_handle_args_root_fallsback_to_instance_data(self, caplog, tmpdir):
        """When no instance_data argument, root falls back to redacted json."""
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=None,
        )
        paths, _, _, _ = self._setup_paths(tmpdir)
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert 1 == query.handle_args("anyname", args)
        json_file = paths.get_runpath("instance_data")
        sensitive_file = paths.get_runpath("instance_data_sensitive")
        msg = (
            f"Missing root-readable {sensitive_file}. "
            f"Using redacted {json_file} instead."
        )
        assert msg in caplog.text

    @pytest.mark.parametrize(
        "ud_src,ud_expected,vd_src,vd_expected",
        (
            ("hi mom", "hi mom", "hi pops", "hi pops"),
            ("ud".encode("utf-8"), "ud", "vd".encode("utf-8"), "vd"),
            (_gzip_data(b"ud"), "ud", _gzip_data(b"vd"), "vd"),
            (_gzip_data("ud".encode("utf-8")), "ud", _gzip_data(b"vd"), "vd"),
        ),
    )
    def test_handle_args_root_processes_user_data(
        self, ud_src, ud_expected, vd_src, vd_expected, capsys, tmpdir
    ):
        """Support reading multiple user-data file content types"""
        paths, _, user_data, vendor_data = self._setup_paths(
            tmpdir, ud_val=ud_src, vd_val=vd_src
        )
        sensitive_file = Path(paths.get_runpath("instance_data_sensitive"))
        sensitive_file.write_text('{"my-var": "it worked"}')
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=user_data.strpath,
            vendor_data=vendor_data.strpath,
            varname=None,
        )
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        cmd_output = json.loads(out)
        assert "it worked" == cmd_output["my-var"]
        if ud_expected == "ci-b64:":
            ud_expected = "ci-b64:{}".format(b64e(ud_src))
        if vd_expected == "ci-b64:":
            vd_expected = "ci-b64:{}".format(b64e(vd_src))
        assert ud_expected == cmd_output["userdata"]
        assert vd_expected == cmd_output["vendordata"]

    def test_handle_args_user_vendor_data_defaults_to_instance_link(
        self, capsys, tmpdir
    ):
        """When no instance_data argument, root uses sensitive json."""
        paths, _, _, _ = self._setup_paths(tmpdir)
        sensitive_file = Path(paths.get_runpath("instance_data_sensitive"))
        sensitive_file.write_text('{"my-var": "it worked"}')

        ud_path = os.path.join(paths.instance_link, "user-data.txt")
        write_file(ud_path, "instance_link_ud")
        vd_path = os.path.join(paths.instance_link, "vendor-data.txt")
        write_file(vd_path, "instance_link_vd")

        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=None,
            vendor_data=None,
            varname=None,
        )
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            with mock.patch("os.getuid", return_value=0):
                assert 0 == query.handle_args("anyname", args)
        expected = (
            '{\n "combined_cloud_config": null,\n "my-var": "it worked",\n '
            '"userdata": "instance_link_ud",\n '
            '"vendordata": "instance_link_vd"\n}\n'
        )
        out, _ = capsys.readouterr()
        assert expected == out

    def test_handle_args_root_uses_instance_sensitive_data(
        self, capsys, tmpdir
    ):
        """When no instance_data argument, root uses sensitive json."""
        paths, _, user_data, vendor_data = self._setup_paths(
            tmpdir, ud_val="ud", vd_val="vd"
        )
        sensitive_file = Path(paths.get_runpath("instance_data_sensitive"))
        sensitive_file.write_text('{"my-var": "it worked"}')
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=None,
            list_keys=False,
            user_data=user_data.strpath,
            vendor_data=vendor_data.strpath,
            varname=None,
        )
        with mock.patch(M_PATH + "read_cfg_paths") as m_paths:
            m_paths.return_value = paths
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert 0 == query.handle_args("anyname", args)
        expected = (
            '{\n "combined_cloud_config": null,\n "my-var": "it worked",\n '
            '"userdata": "ud",\n "vendordata": "vd"\n}\n'
        )
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_dumps_all_instance_data(self, capsys, tmpdir):
        """When --all is specified query will dump all instance data vars."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write('{"my-var": "it worked"}')
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        expected = (
            '{\n "combined_cloud_config": "<redacted for non-root user> file:'
            '/run/cloud-init/combined-cloud-config.json",\n "my-var":'
            ' "it worked",\n "userdata": "<%s> file:ud",\n'
            ' "vendordata": "<%s> file:vd"\n}\n'
            % (REDACT_SENSITIVE_VALUE, REDACT_SENSITIVE_VALUE)
        )
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_returns_top_level_varname(self, capsys, tmpdir):
        """When the argument varname is passed, report its value."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write('{"my-var": "it worked"}')
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname="my_var",
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert "it worked\n" == out

    @pytest.mark.parametrize(
        "inst_data,varname,expected",
        (
            (
                '{"v1": {"key-2": "value-2"}, "my-var": "it worked"}',
                "v1.key_2",
                "value-2\n",
            ),
            # Assert no jinja underscore-delimited aliases are reported on CLI
            (
                '{"v1": {"something-hyphenated": {"no.underscores":"x",'
                ' "no-alias": "y"}}, "my-var": "it worked"}',
                "v1.something_hyphenated",
                '{\n "no-alias": "y",\n "no.underscores": "x"\n}\n',
            ),
        ),
    )
    def test_handle_args_returns_nested_varname(
        self, inst_data, varname, expected, capsys, tmpdir
    ):
        """If user_data file is a jinja template render instance-data vars."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(inst_data)
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=instance_data.strpath,
            user_data="ud",
            vendor_data="vd",
            list_keys=False,
            varname=varname,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_returns_standardized_vars_to_top_level_aliases(
        self, capsys, tmpdir
    ):
        """Any standardized vars under v# are promoted as top-level aliases."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}'
        )
        expected = dedent(
            """\
            {
             "combined_cloud_config": "<redacted for non-root user> %s",
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
        """
            % "file:/run/cloud-init/combined-cloud-config.json"
        )
        args = self.Args(
            debug=False,
            dump_all=True,
            format=None,
            instance_data=instance_data.strpath,
            user_data="ud",
            vendor_data="vd",
            list_keys=False,
            varname=None,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_sorts_top_level_keys_when_no_varname(
        self, capsys, tmpdir
    ):
        """Sort all top-level keys when only --list-keys provided."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1"}, "v2": {"v2_2": "val2.2"},'
            ' "top": "gun"}'
        )
        expected = (
            "combined_cloud_config\ntop\nuserdata\nv1\nv1_1\nv2\nv2_2\n"
            "vendordata\n"
        )
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=True,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_sorts_nested_keys_when_varname(
        self, capsys, tmpdir
    ):
        """Sort all nested keys of varname object when --list-keys provided."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2":'
            ' {"v2_2": "val2.2"}, "top": "gun"}'
        )
        expected = "v1_1\nv1_2\n"
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=True,
            user_data="ud",
            vendor_data="vd",
            varname="v1",
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_list_keys_errors_when_varname_is_not_a_dict(
        self, caplog, tmpdir
    ):
        """Raise an error when --list-keys and varname specify a non-list."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": '
            '{"v2_2": "val2.2"}, "top": "gun"}'
        )
        expected_error = "--list-keys provided but 'top' is not a dict"
        args = self.Args(
            debug=False,
            dump_all=False,
            format=None,
            instance_data=instance_data.strpath,
            list_keys=True,
            user_data="ud",
            vendor_data="vd",
            varname="top",
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 1 == query.handle_args("anyname", args)
        assert expected_error in caplog.text

    @pytest.mark.parametrize(
        "header_included",
        [True, False],
    )
    def test_handle_args_formats_jinja_successfully(
        self, caplog, tmpdir, capsys, header_included
    ):
        """Test that rendering a jinja template works as expected."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": '
            '{"v2_2": "val2.2"}, "top": "gun"}'
        )
        header = "## template: jinja\n" if header_included else ""
        format = header + "v1_1: {{ v1.v1_1 }}"
        expected = header + "v1_1: val1.1\n"

        args = self.Args(
            debug=False,
            dump_all=False,
            format=format,
            instance_data=instance_data.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 0 == query.handle_args("anyname", args)
        out, _err = capsys.readouterr()
        assert expected == out

    def test_handle_args_invalid_jinja_exception(self, caplog, tmpdir, capsys):
        """Raise an error when a jinja syntax error is encountered."""
        instance_data = tmpdir.join("instance-data")
        instance_data.write(
            '{"v1": {"v1_1": "val1.1", "v1_2": "val1.2"}, "v2": '
            '{"v2_2": "val2.2"}, "top": "gun"}'
        )
        format = "v1_1: {{ v1.v1_1 } }"
        expected_error = (
            "Failed to render templated data. "
            + JinjaSyntaxParsingException.format_error_message(
                syntax_error="unexpected '}'",
                line_number=2,
                line_content="v1_1: {{ v1.v1_1 } }",
            )
        )
        args = self.Args(
            debug=False,
            dump_all=False,
            format=format,
            instance_data=instance_data.strpath,
            list_keys=False,
            user_data="ud",
            vendor_data="vd",
            varname=None,
        )
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 100
            assert 1 == query.handle_args("anyname", args)
        assert expected_error in caplog.text
