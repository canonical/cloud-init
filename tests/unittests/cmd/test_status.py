# This file is part of cloud-init. See LICENSE file for license information.

import errno
import os
from collections import namedtuple
from io import StringIO
from textwrap import dedent
from typing import Callable, Dict, Optional, Union
from unittest import mock

import pytest

from cloudinit.atomic_helper import write_json
from cloudinit.cmd import status
from cloudinit.util import ensure_file
from tests.unittests.helpers import wrap_and_call

M_NAME = "cloudinit.cmd.status"
M_PATH = f"{M_NAME}."

MyPaths = namedtuple("MyPaths", "run_dir")
MyArgs = namedtuple("MyArgs", "long wait")
Config = namedtuple(
    "Config", "new_root, status_file, disable_file, result_file, paths"
)


@pytest.fixture(scope="function")
def config(tmpdir):
    return Config(
        new_root=tmpdir,
        status_file=tmpdir.join("status.json"),
        disable_file=tmpdir.join("cloudinit-disable"),
        result_file=tmpdir.join("result.json"),
        paths=MyPaths(run_dir=tmpdir),
    )


class TestStatus:
    @pytest.mark.parametrize(
        [
            "ensured_file",
            "uses_systemd",
            "get_cmdline",
            "expected_is_disabled",
            "is_disabled_msg",
            "expected_reason",
        ],
        [
            # When not in an environment using systemd, return False.
            pytest.param(
                lambda config: config.disable_file,
                False,
                "root=/dev/my-root not-important",
                False,
                "expected enabled cloud-init on sysvinit",
                "Cloud-init enabled on sysvinit",
                id="false_on_sysvinit",
            ),
            # When using systemd and disable_file is present return disabled.
            pytest.param(
                lambda config: config.disable_file,
                True,
                "root=/dev/my-root not-important",
                True,
                "expected disabled cloud-init",
                lambda config: f"Cloud-init disabled by {config.disable_file}",
                id="true_on_disable_file",
            ),
            # Not disabled when using systemd and enabled via commandline.
            pytest.param(
                lambda config: config.disable_file,
                True,
                "something cloud-init=enabled else",
                False,
                "expected enabled cloud-init",
                "Cloud-init enabled by kernel command line cloud-init=enabled",
                id="false_on_kernel_cmdline_enable",
            ),
            # When kernel command line disables cloud-init return True.
            pytest.param(
                None,
                True,
                "something cloud-init=disabled else",
                True,
                "expected disabled cloud-init",
                "Cloud-init disabled by kernel parameter cloud-init=disabled",
                id="true_on_kernel_cmdline",
            ),
            # When cloud-init-generator writes disabled file return True.
            pytest.param(
                lambda config: os.path.join(config.paths.run_dir, "disabled"),
                True,
                "something",
                True,
                "expected disabled cloud-init",
                "Cloud-init disabled by cloud-init-generator",
                id="true_when_generator_disables",
            ),
            # Report enabled when systemd generator creates the enabled file.
            pytest.param(
                lambda config: os.path.join(config.paths.run_dir, "enabled"),
                True,
                "something ignored",
                False,
                "expected enabled cloud-init",
                "Cloud-init enabled by systemd cloud-init-generator",
                id="false_when_enabled_in_systemd",
            ),
        ],
    )
    def test__is_cloudinit_disabled(
        self,
        ensured_file: Optional[Callable],
        uses_systemd: bool,
        get_cmdline: str,
        expected_is_disabled: bool,
        is_disabled_msg: str,
        expected_reason: Union[str, Callable],
        config: Config,
    ):
        if ensured_file is not None:
            ensure_file(ensured_file(config))
        (is_disabled, reason) = wrap_and_call(
            M_NAME,
            {
                "uses_systemd": uses_systemd,
                "get_cmdline": get_cmdline,
            },
            status._is_cloudinit_disabled,
            config.disable_file,
            config.paths,
        )
        assert is_disabled == expected_is_disabled, is_disabled_msg
        if isinstance(expected_reason, str):
            assert reason == expected_reason
        else:
            assert reason == expected_reason(config)

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_returns_not_run(self, m_read_cfg_paths, config: Config):
        """When status.json does not exist yet, return 'not run'."""
        m_read_cfg_paths.return_value = config.paths
        assert not os.path.exists(
            config.status_file
        ), "Unexpected status.json found"
        cmdargs = MyArgs(long=False, wait=False)
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                M_NAME,
                {"_is_cloudinit_disabled": (False, "")},
                status.handle_status_args,
                "ignored",
                cmdargs,
            )
        assert retcode == 0
        assert m_stdout.getvalue() == "status: not run\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_returns_disabled_long_on_presence_of_disable_file(
        self, m_read_cfg_paths, config: Config
    ):
        """When cloudinit is disabled, return disabled reason."""
        m_read_cfg_paths.return_value = config.paths
        checked_files = []

        def fakeexists(filepath):
            checked_files.append(filepath)
            status_file = os.path.join(config.paths.run_dir, "status.json")
            return bool(not filepath == status_file)

        cmdargs = MyArgs(long=True, wait=False)
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                M_NAME,
                {
                    "os.path.exists": {"side_effect": fakeexists},
                    "_is_cloudinit_disabled": (
                        True,
                        "disabled for some reason",
                    ),
                },
                status.handle_status_args,
                "ignored",
                cmdargs,
            )
        assert retcode == 0
        assert checked_files == [
            os.path.join(config.paths.run_dir, "status.json")
        ]
        expected = dedent(
            """\
            status: disabled
            detail:
            disabled for some reason
        """
        )
        assert m_stdout.getvalue() == expected

    @pytest.mark.parametrize(
        [
            "ensured_file",
            "status_content",
            "assert_file",
            "cmdargs",
            "expected_retcode",
            "expected_status",
        ],
        [
            # Report running when status.json exists but result.json does not.
            pytest.param(
                None,
                {},
                lambda config: config.result_file,
                MyArgs(long=False, wait=False),
                0,
                "status: running\n",
                id="running_on_no_results_json",
            ),
            # Report running when status exists with an unfinished stage.
            pytest.param(
                lambda config: config.result_file,
                {"v1": {"init": {"start": 1, "finished": None}}},
                None,
                MyArgs(long=False, wait=False),
                0,
                "status: running\n",
                id="running",
            ),
            # Report done results.json exists no stages are unfinished.
            pytest.param(
                lambda config: config.result_file,
                {
                    "v1": {
                        "stage": None,  # No current stage running
                        "datasource": (
                            "DataSourceNoCloud "
                            "[seed=/var/.../seed/nocloud-net]"
                            "[dsmode=net]"
                        ),
                        "blah": {"finished": 123.456},
                        "init": {
                            "errors": [],
                            "start": 124.567,
                            "finished": 125.678,
                        },
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=False, wait=False),
                0,
                "status: done\n",
                id="done",
            ),
            # Long format of done status includes datasource info.
            pytest.param(
                lambda config: config.result_file,
                {
                    "v1": {
                        "stage": None,
                        "datasource": (
                            "DataSourceNoCloud "
                            "[seed=/var/.../seed/nocloud-net]"
                            "[dsmode=net]"
                        ),
                        "init": {"start": 124.567, "finished": 125.678},
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=True, wait=False),
                0,
                dedent(
                    """\
                    status: done
                    time: Thu, 01 Jan 1970 00:02:05 +0000
                    detail:
                    DataSourceNoCloud [seed=/var/.../seed/nocloud-net]\
[dsmode=net]
                    """
                ),
                id="returns_done_long",
            ),
            # Reports error when any stage has errors.
            pytest.param(
                None,
                {
                    "v1": {
                        "stage": None,
                        "blah": {"errors": [], "finished": 123.456},
                        "init": {
                            "errors": ["error1"],
                            "start": 124.567,
                            "finished": 125.678,
                        },
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=False, wait=False),
                1,
                "status: error\n",
                id="on_errors",
            ),
            # Long format of error status includes all error messages.
            pytest.param(
                None,
                {
                    "v1": {
                        "stage": None,
                        "datasource": (
                            "DataSourceNoCloud "
                            "[seed=/var/.../seed/nocloud-net]"
                            "[dsmode=net]"
                        ),
                        "init": {
                            "errors": ["error1"],
                            "start": 124.567,
                            "finished": 125.678,
                        },
                        "init-local": {
                            "errors": ["error2", "error3"],
                            "start": 123.45,
                            "finished": 123.46,
                        },
                    }
                },
                None,
                MyArgs(long=True, wait=False),
                1,
                dedent(
                    """\
                    status: error
                    time: Thu, 01 Jan 1970 00:02:05 +0000
                    detail:
                    error1
                    error2
                    error3
                    """
                ),
                id="on_errors_long",
            ),
            # Long format reports the stage in which we are running.
            pytest.param(
                None,
                {
                    "v1": {
                        "stage": "init",
                        "init": {"start": 124.456, "finished": None},
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=True, wait=False),
                0,
                dedent(
                    """\
                    status: running
                    time: Thu, 01 Jan 1970 00:02:04 +0000
                    detail:
                    Running in stage: init
                    """
                ),
                id="running_long_format",
            ),
        ],
    )
    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_output(
        self,
        m_read_cfg_paths,
        ensured_file: Optional[Callable],
        status_content: Dict,
        assert_file,
        cmdargs: MyArgs,
        expected_retcode: int,
        expected_status: str,
        config: Config,
    ):
        m_read_cfg_paths.return_value = config.paths
        if ensured_file:
            ensure_file(ensured_file(config))
        write_json(
            config.status_file,
            status_content,
        )
        if assert_file:
            assert not os.path.exists(
                config.result_file
            ), f"Unexpected {config.result_file} found"
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                M_NAME,
                {"_is_cloudinit_disabled": (False, "")},
                status.handle_status_args,
                "ignored",
                cmdargs,
            )
        assert retcode == expected_retcode
        assert m_stdout.getvalue() == expected_status

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_wait_blocks_until_done(
        self, m_read_cfg_paths, config: Config
    ):
        """Specifying wait will poll every 1/4 second until done state."""
        m_read_cfg_paths.return_value = config.paths
        running_json = {
            "v1": {
                "stage": "init",
                "init": {"start": 124.456, "finished": None},
                "init-local": {"start": 123.45, "finished": 123.46},
            }
        }
        done_json = {
            "v1": {
                "stage": None,
                "init": {"start": 124.456, "finished": 125.678},
                "init-local": {"start": 123.45, "finished": 123.46},
            }
        }

        sleep_calls = 0

        def fake_sleep(interval):
            nonlocal sleep_calls
            assert interval == 0.25
            sleep_calls += 1
            if sleep_calls == 2:
                write_json(config.status_file, running_json)
            elif sleep_calls == 3:
                write_json(config.status_file, done_json)
                result_file = config.result_file
                ensure_file(result_file)

        cmdargs = MyArgs(long=False, wait=True)
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                M_NAME,
                {
                    "sleep": {"side_effect": fake_sleep},
                    "_is_cloudinit_disabled": (False, ""),
                },
                status.handle_status_args,
                "ignored",
                cmdargs,
            )
        assert retcode == 0
        assert sleep_calls == 4
        assert m_stdout.getvalue() == "....\nstatus: done\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_wait_blocks_until_error(
        self, m_read_cfg_paths, config: Config
    ):
        """Specifying wait will poll every 1/4 second until error state."""
        m_read_cfg_paths.return_value = config.paths
        running_json = {
            "v1": {
                "stage": "init",
                "init": {"start": 124.456, "finished": None},
                "init-local": {"start": 123.45, "finished": 123.46},
            }
        }
        error_json = {
            "v1": {
                "stage": None,
                "init": {
                    "errors": ["error1"],
                    "start": 124.456,
                    "finished": 125.678,
                },
                "init-local": {"start": 123.45, "finished": 123.46},
            }
        }

        sleep_calls = 0

        def fake_sleep(interval):
            nonlocal sleep_calls
            assert interval == 0.25
            sleep_calls += 1
            if sleep_calls == 2:
                write_json(config.status_file, running_json)
            elif sleep_calls == 3:
                write_json(config.status_file, error_json)

        cmdargs = MyArgs(long=False, wait=True)
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            retcode = wrap_and_call(
                M_NAME,
                {
                    "sleep": {"side_effect": fake_sleep},
                    "_is_cloudinit_disabled": (False, ""),
                },
                status.handle_status_args,
                "ignored",
                cmdargs,
            )
        assert retcode == 1
        assert sleep_calls == 4
        assert m_stdout.getvalue() == "....\nstatus: error\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_main(self, m_read_cfg_paths, config: Config):
        """status.main can be run as a standalone script."""
        m_read_cfg_paths.return_value = config.paths
        write_json(
            config.status_file,
            {"v1": {"init": {"start": 1, "finished": None}}},
        )
        with pytest.raises(SystemExit) as e:
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                wrap_and_call(
                    M_NAME,
                    {
                        "sys.argv": {"new": ["status"]},
                        "_is_cloudinit_disabled": (False, ""),
                    },
                    status.main,
                )
        assert e.value.code == 0
        assert m_stdout.getvalue() == "status: running\n"

    @mock.patch(
        "cloudinit.cmd.devel.Init.read_cfg",
        side_effect=OSError(errno.EACCES, "Not allowed"),
    )
    def test_status_no_read_permission_init_config(self, m_read_cfg):
        """status.handle_status_args outputs to stderr and exists with 1 if
        some init cfg file has no user permissions.
        """

        cmdargs = MyArgs(long=False, wait=True)
        with mock.patch("sys.stderr", new_callable=StringIO) as m_stderr:
            with pytest.raises(SystemExit) as exc_info:
                wrap_and_call(
                    M_NAME,
                    {
                        "sleep": {"side_effect": lambda *_: None},
                        "_is_cloudinit_disabled": (False, ""),
                    },
                    status.handle_status_args,
                    "ignored",
                    cmdargs,
                )
        assert exc_info.value.code == 1
        expected_error = (
            "Error:\nFailed reading config file(s) due to permission error:\n"
            "[Errno 13] Not allowed\n"
        )
        assert m_stderr.getvalue() == expected_error
        assert m_read_cfg.call_count == 1

    @mock.patch(
        "cloudinit.cmd.devel.Init.read_cfg",
        side_effect=OSError(errno.EACCES, "Not allowed"),
    )
    def test_get_status_details_no_read_permission_init_config(
        self, m_read_cfg
    ):
        """status.get_status_details outputs to stderr and exists with 1 if
        some init cfg file has no user permissions.
        """
        with mock.patch("sys.stderr", new_callable=StringIO) as m_stderr:
            with pytest.raises(SystemExit) as exc_info:
                status.get_status_details()
        assert exc_info.value.code == 1
        expected_error = (
            "Error:\nFailed reading config file(s) due to permission error:\n"
            "[Errno 13] Not allowed\n"
        )
        assert m_stderr.getvalue() == expected_error
        assert m_read_cfg.call_count == 1


# vi: ts=4 expandtab syntax=python
