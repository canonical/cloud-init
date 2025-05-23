# This file is part of cloud-init. See LICENSE file for license information.

import contextlib
import io
import json
import logging
import os
import sys
from collections import namedtuple

import pytest

from cloudinit import helpers
from cloudinit.cmd import main as cli
from tests.unittests import helpers as test_helpers

mock = test_helpers.mock

M_PATH = "cloudinit.cmd.main."
Tmpdir = namedtuple("Tmpdir", ["tmpdir", "link_d", "data_d"])
FakeArgs = namedtuple("FakeArgs", ["action", "local", "mode"])


@pytest.fixture(autouse=True, scope="module")
def disable_setup_logging():
    # setup_basic_logging can change the logging level to WARNING, so
    # ensure it is always mocked
    with mock.patch(f"{M_PATH}loggers.setup_basic_logging", autospec=True):
        yield


@pytest.fixture()
def mock_status_wrapper(mocker, tmpdir):
    link_d = os.path.join(tmpdir, "link")
    data_d = os.path.join(tmpdir, "data")
    mocker.patch(
        "cloudinit.cmd.main.read_cfg_paths",
        return_value=mock.Mock(get_cpath=lambda _: data_d),
    )
    mocker.patch("cloudinit.cmd.main.os.path.normpath", return_value=link_d)
    yield Tmpdir(tmpdir, link_d, data_d)


class TestCLI:
    def _call_main(self, sysv_args=None):
        if not sysv_args:
            sysv_args = ["cloud-init"]
        try:
            return cli.main(sysv_args=sysv_args)
        except SystemExit as e:
            return e.code

    @pytest.mark.parametrize(
        "action,name,match",
        [
            pytest.param(
                "doesnotmatter",
                "init1",
                "^unknown name: init1$",
                id="invalid_name",
            ),
            pytest.param(
                "modules_name",
                "modules",
                "^Invalid cloud init mode specified 'modules-bogusmode'$",
                id="invalid_modes",
            ),
        ],
    )
    def test_status_wrapper_errors(
        self, action, name, match, caplog, mock_status_wrapper
    ):
        my_action = mock.Mock()

        myargs = FakeArgs((action, my_action), False, "bogusmode")
        with pytest.raises(ValueError, match=match):
            cli.status_wrapper(name, myargs)
        assert [] == my_action.call_args_list

    @mock.patch("cloudinit.cmd.main.atomic_helper.write_json")
    def test_status_wrapper_init_local_writes_fresh_status_info(
        self,
        m_json,
        mock_status_wrapper,
    ):
        """When running in init-local mode, status_wrapper writes status.json.

        Old status and results artifacts are also removed.
        """
        data_d = mock_status_wrapper.data_d
        link_d = mock_status_wrapper.link_d
        # Write old artifacts which will be removed or updated.
        for _dir in data_d, link_d:
            test_helpers.populate_dir(
                str(_dir), {"status.json": "old", "result.json": "old"}
            )

        def myaction(name, args):
            # Return an error to watch status capture them
            return "SomeDatasource", ["an error"]

        myargs = FakeArgs(("ignored_name", myaction), True, "bogusmode")
        cli.status_wrapper("init", myargs)
        # No errors reported in status
        status_v1 = m_json.call_args_list[1][0][1]["v1"]
        assert status_v1.keys() == {
            "datasource",
            "init-local",
            "init",
            "modules-config",
            "modules-final",
            "stage",
        }
        assert ["an error"] == status_v1["init-local"]["errors"]
        assert "SomeDatasource" == status_v1["datasource"]
        assert False is os.path.exists(
            data_d.join("result.json")
        ), "unexpected result.json found"
        assert False is os.path.exists(
            link_d.join("result.json")
        ), "unexpected result.json link found"

    @mock.patch("cloudinit.cmd.main.atomic_helper.write_json")
    def test_status_wrapper_init_local_honor_cloud_dir(
        self, m_json, mocker, mock_status_wrapper
    ):
        """When running in init-local mode, status_wrapper honors cloud_dir."""
        cloud_dir = mock_status_wrapper.tmpdir.join("cloud")
        paths = helpers.Paths({"cloud_dir": str(cloud_dir)})
        mocker.patch(
            "cloudinit.config.schema.read_cfg_paths", return_value=paths
        )
        data_d = mock_status_wrapper.data_d
        link_d = mock_status_wrapper.link_d

        def myaction(name, args):
            # Return an error to watch status capture them
            return "SomeDatasource", ["an_error"]

        myargs = FakeArgs(("ignored_name", myaction), True, "bogusmode")
        cli.status_wrapper("init", myargs)  # No explicit data_d

        # Access cloud_dir directly
        status_v1 = m_json.call_args_list[1][0][1]["v1"]
        assert ["an_error"] == status_v1["init-local"]["errors"]
        assert "SomeDatasource" == status_v1["datasource"]
        assert False is os.path.exists(
            data_d.join("result.json")
        ), "unexpected result.json found"
        assert False is os.path.exists(
            link_d.join("result.json")
        ), "unexpected result.json link found"

    def test_no_arguments_shows_usage(self, capsys):
        exit_code = self._call_main()
        _out, err = capsys.readouterr()
        assert "usage: cloud-init" in err
        assert 2 == exit_code

    def test_no_arguments_shows_error_message(self, capsys):
        exit_code = self._call_main()
        missing_subcommand_message = "a subcommand is required"
        _out, err = capsys.readouterr()
        assert (
            missing_subcommand_message in err
        ), "Did not find error message for missing subcommand"
        assert 2 == exit_code

    def test_all_subcommands_represented_in_help(self, capsys):
        """All known subparsers are represented in the cloud-int help doc."""
        self._call_main()
        _out, err = capsys.readouterr()
        expected_subcommands = [
            "analyze",
            "clean",
            "devel",
            "features",
            "init",
            "modules",
            "single",
            "schema",
        ]
        for subcommand in expected_subcommands:
            assert subcommand in err

    @pytest.mark.parametrize(
        "subcommand,log_to_stderr,mocks",
        (
            ("init", False, [mock.patch("cloudinit.cmd.main.status_wrapper")]),
            (
                "modules",
                False,
                [mock.patch("cloudinit.cmd.main.status_wrapper")],
            ),
            (
                "schema",
                True,
                [
                    mock.patch(
                        "cloudinit.stages.Init._read_cfg", return_value={}
                    ),
                    mock.patch("cloudinit.config.schema.handle_schema_args"),
                ],
            ),
        ),
    )
    @mock.patch("cloudinit.cmd.main.loggers.setup_basic_logging")
    def test_subcommands_log_to_stderr_via_setup_basic_logging(
        self, setup_basic_logging, subcommand, log_to_stderr, mocks
    ):
        """setup_basic_logging is called for modules to use stderr

        Subcommands with exception of 'init'  and 'modules' use
        setup_basic_logging to direct logged errors to stderr.
        """
        with contextlib.ExitStack() as mockstack:
            for mymock in mocks:
                mockstack.enter_context(mymock)
            self._call_main(["cloud-init", subcommand])
        if log_to_stderr:
            setup_basic_logging.assert_called_once_with(logging.WARNING)
        else:
            setup_basic_logging.assert_not_called()

    @pytest.mark.parametrize("subcommand", ["init", "modules"])
    @mock.patch("cloudinit.cmd.main.status_wrapper")
    def test_modules_subcommand_parser(self, m_status_wrapper, subcommand):
        """The subcommand 'subcommand' calls status_wrapper passing modules."""
        self._call_main(["cloud-init", subcommand])
        (name, parseargs) = m_status_wrapper.call_args_list[0][0]
        assert subcommand == name
        assert subcommand == parseargs.subcommand
        assert subcommand == parseargs.action[0]
        assert f"main_{subcommand}" == parseargs.action[1].__name__

    @pytest.mark.parametrize(
        "subcommand",
        [
            "analyze",
            "clean",
            "collect-logs",
            "devel",
            "status",
            "schema",
        ],
    )
    def test_conditional_subcommands_from_entry_point_sys_argv(
        self,
        subcommand,
        capsys,
        mock_status_wrapper,
    ):
        """Subcommands from entry-point are properly parsed from sys.argv."""
        expected_error = f"usage: cloud-init {subcommand}"
        # The cloud-init entrypoint calls main without passing sys_argv
        with mock.patch("sys.argv", ["cloud-init", subcommand, "-h"]):
            try:
                cli.main()
            except SystemExit as e:
                assert 0 == e.code  # exit 2 on proper -h usage
        out, _err = capsys.readouterr()
        assert expected_error in out

    @pytest.mark.parametrize(
        "subcommand",
        [
            "clean",
            "collect-logs",
            "status",
        ],
    )
    def test_subcommand_parser(self, subcommand, mock_status_wrapper):
        """cloud-init `subcommand` calls its subparser."""
        # Provide -h param to `subcommand` to avoid having to mock behavior.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self._call_main(["cloud-init", subcommand, "-h"])
        assert f"usage: cloud-init {subcommand}" in out.getvalue()

    @pytest.mark.parametrize(
        "subcommand",
        [
            "clean",
            "collect-logs",
            "status",
        ],
    )
    def test_subcommand_parser_shows_usage(self, subcommand, capsys):
        """cloud-init `subcommand` shows usage on error."""
        # Provide --invalid-arg to `subcommand` to trigger error.
        exit_code = self._call_main(["cloud-init", subcommand, "--invalid"])
        _out, err = capsys.readouterr()
        assert f"usage: cloud-init {subcommand}" in err
        assert 2 == exit_code

    @pytest.mark.parametrize(
        "args,expected_subcommands",
        [
            ([], ["schema"]),
            (["analyze"], ["blame", "show", "dump"]),
        ],
    )
    def test_subcommand_parser_multi_arg(
        self, args, expected_subcommands, capsys
    ):
        """The subcommand cloud-init schema calls the correct subparser."""
        self._call_main(["cloud-init"] + args)
        _out, err = capsys.readouterr()
        for subcommand in expected_subcommands:
            assert subcommand in err

    @mock.patch("cloudinit.stages.Init._read_cfg", return_value={})
    def test_wb_schema_subcommand_parser(self, m_read_cfg, capsys):
        """The subcommand cloud-init schema calls the correct subparser."""
        exit_code = self._call_main(["cloud-init", "schema"])
        _out, err = capsys.readouterr()
        assert 1 == exit_code
        # Known whitebox output from schema subcommand
        assert (
            "Error:\n"
            "Expected one of --config-file or --system arguments\n" in err
        )

    @mock.patch("cloudinit.cmd.main.main_single")
    def test_single_subcommand(self, m_main_single):
        """The subcommand 'single' calls main_single with valid args."""
        self._call_main(["cloud-init", "single", "--name", "cc_ntp"])
        (name, parseargs) = m_main_single.call_args_list[0][0]
        assert "single" == name
        assert "single" == parseargs.subcommand
        assert "single" == parseargs.action[0]
        assert False is parseargs.debug
        assert False is parseargs.force
        assert None is parseargs.frequency
        assert "cc_ntp" == parseargs.name
        assert False is parseargs.report

    @mock.patch("cloudinit.cmd.main.main_features")
    def test_features_hook_subcommand(self, m_features):
        """The subcommand 'features' calls main_features with args."""
        self._call_main(["cloud-init", "features"])
        (name, parseargs) = m_features.call_args_list[0][0]
        assert "features" == name
        assert "features" == parseargs.subcommand
        assert "features" == parseargs.action[0]
        assert False is parseargs.debug
        assert False is parseargs.force

    def test_all_stages_with_tty(self, mocker):
        """Ensure all stages get called when using a tty."""
        mocker.patch("cloudinit.cmd.main.os.isatty", return_value=True)
        mocker.patch("cloudinit.cmd.main.sys.stdin.fileno")
        mocker.patch("cloudinit.cmd.main.socket.sd_notify")
        mocker.patch("cloudinit.cmd.main.socket.os.makedirs")
        mocker.patch("cloudinit.cmd.main.socket.os.remove")
        mocker.patch("cloudinit.cmd.main.socket.socket")
        m_sub_main = mocker.patch(
            "cloudinit.cmd.main.sub_main", return_value=0
        )

        self._call_main(["cloud-init", "--all-stages"])
        assert m_sub_main.call_count == 4
        assert m_sub_main.call_args_list[0][0][0].subcommand == "init"
        assert m_sub_main.call_args_list[0][0][0].local is True

        assert m_sub_main.call_args_list[1][0][0].subcommand == "init"
        assert m_sub_main.call_args_list[1][0][0].local is False

        assert m_sub_main.call_args_list[2][0][0].subcommand == "modules"
        assert m_sub_main.call_args_list[2][0][0].mode == "config"

        assert m_sub_main.call_args_list[3][0][0].subcommand == "modules"
        assert m_sub_main.call_args_list[3][0][0].mode == "final"


class TestSignalHandling:
    @mock.patch("cloudinit.cmd.main.atomic_helper.write_json")
    def test_status_wrapper_signal_sys_exit(
        self,
        m_json,
        mocker,
        mock_status_wrapper,
    ):
        """make sure that when sys.exit(N) is called, the correct code is
        returned
        """
        for code in [1, 2, 3, 4]:
            rc = cli.status_wrapper(
                "init",
                FakeArgs(
                    (
                        None,
                        # silence pylint false positive
                        # https://github.com/pylint-dev/pylint/issues/9557
                        lambda *_: sys.exit(code),  # pylint: disable=W0640
                    ),
                    False,
                    "bogusmode",
                ),
            )
            assert 1 == rc

            # assert that the status shows errors
            assert (
                f"sys.exit({code}) called"
                in m_json.call_args[0][1]["v1"]["init"]["errors"]
            )

    @mock.patch("cloudinit.cmd.main.atomic_helper.write_json")
    def test_status_wrapper_no_signal_sys_exit(
        self,
        m_json,
        mock_status_wrapper,
    ):
        """if sys.exit(0) is called, make sure that cloud-init doesn't log a
        warning"""
        # call status_wrapper() with the required args
        rc = cli.status_wrapper(
            "init",
            FakeArgs(
                (
                    None,
                    lambda *_: sys.exit(0),
                ),
                False,
                "bogusmode",
            ),
        )
        assert 0 == rc
        assert not m_json.call_args[0][1]["v1"]["init"]["errors"]

    @mock.patch("cloudinit.cmd.main.atomic_helper.write_json")
    def test_status_wrapper_signal_warnings(
        self,
        m_json,
        mock_status_wrapper,
    ):
        """If a stage is started and status.json already has a start time but
        no end time for that stage, this is an unknown state - make sure that
        a warning is logged.
        """

        # Write a status.json to the mocked temporary directory
        for dir in mock_status_wrapper.data_d, mock_status_wrapper.link_d:
            test_helpers.populate_dir(
                str(dir),
                {
                    "status.json": json.dumps(
                        {
                            "v1": {
                                "stage": "init",
                                "datasource": (
                                    "DataSourceNoCloud "
                                    "[seed=/var/.../seed/nocloud-net]"
                                    "[dsmode=net]"
                                ),
                                "init": {
                                    "errors": [],
                                    "recoverable_errors": {},
                                    "start": 124.567,
                                    "finished": None,
                                },
                                "init-local": {
                                    "errors": [],
                                    "recoverable_errors": {},
                                    "start": 100.0,
                                    "finished": 100.00001,
                                },
                                "modules-config": {
                                    "errors": [],
                                    "recoverable_errors": {},
                                    "start": None,
                                    "finished": None,
                                },
                                "modules-final": {
                                    "errors": [],
                                    "recoverable_errors": {},
                                    "start": None,
                                    "finished": None,
                                },
                            }
                        }
                    )
                },
            )
        # call status_wrapper() with the required args
        cli.status_wrapper(
            "init",
            FakeArgs(
                (
                    None,
                    lambda *_: ("SomeDataSource", []),
                ),
                False,
                "bogusmode",
            ),
        )

        # assert that the status shows recoverable errors
        assert (
            "Unexpected start time found for Network Stage. "
            "Was this stage restarted?"
            in m_json.call_args[0][1]["v1"]["init"]["recoverable_errors"][
                "WARNING"
            ]
        )
