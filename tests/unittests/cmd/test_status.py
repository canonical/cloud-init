# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
from collections import namedtuple
from textwrap import dedent
from typing import Callable, Dict, Optional, Union
from unittest import mock

import pytest

from cloudinit.atomic_helper import write_json
from cloudinit.cmd import status
from cloudinit.cmd.status import UXAppStatus, _get_systemd_status
from cloudinit.subp import SubpResult
from cloudinit.util import ensure_file
from tests.unittests.helpers import wrap_and_call

M_NAME = "cloudinit.cmd.status"
M_PATH = f"{M_NAME}."

MyPaths = namedtuple("MyPaths", "run_dir")
MyArgs = namedtuple("MyArgs", "long wait format")
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
    maxDiff = None

    @mock.patch(
        M_PATH + "load_file",
        return_value=(
            '{"v1": {"datasource": null, "init": {"errors": [], "finished": '
            'null, "start": null}, "init-local": {"errors": [], "finished": '
            'null, "start": 1669231096.9621563}, "modules-config": '
            '{"errors": [], "finished": null, "start": null},'
            '"modules-final": {"errors": [], "finished": null, '
            '"start": null}, "modules-init": {"errors": [], "finished": '
            'null, "start": null}, "stage": "init-local"} }'
        ),
    )
    @mock.patch(M_PATH + "os.path.exists", return_value=True)
    @mock.patch(
        M_PATH + "get_bootstatus",
        return_value=(
            status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
            "Cloud-init enabled by systemd cloud-init-generator",
        ),
    )
    @mock.patch(f"{M_PATH}_get_systemd_status", return_value=None)
    def test_get_status_details_ds_none(
        self,
        m_get_systemd_status,
        m_get_boot_status,
        m_p_exists,
        m_load_json,
        tmpdir,
    ):
        paths = mock.Mock()
        paths.run_dir = str(tmpdir)
        assert status.StatusDetails(
            status.UXAppStatus.RUNNING,
            status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
            "Running in stage: init-local",
            [],
            "Wed, 23 Nov 2022 19:18:16 +0000",
            None,  # datasource
        ) == status.get_status_details(paths)

    @pytest.mark.parametrize(
        [
            "ensured_file",
            "uses_systemd",
            "get_cmdline",
            "expected_bootstatus",
            "failure_msg",
            "expected_reason",
        ],
        [
            # When not in an environment using systemd, return False.
            pytest.param(
                lambda config: config.disable_file,
                False,
                "root=/dev/my-root not-important",
                status.UXAppBootStatusCode.ENABLED_BY_SYSVINIT,
                "expected enabled cloud-init on sysvinit",
                "Cloud-init enabled on sysvinit",
                id="false_on_sysvinit",
            ),
            # When using systemd and disable_file is present return disabled.
            pytest.param(
                lambda config: config.disable_file,
                True,
                "root=/dev/my-root not-important",
                status.UXAppBootStatusCode.DISABLED_BY_MARKER_FILE,
                "expected disabled cloud-init",
                lambda config: f"Cloud-init disabled by {config.disable_file}",
                id="true_on_disable_file",
            ),
            # Not disabled when using systemd and enabled via commandline.
            pytest.param(
                lambda config: config.disable_file,
                True,
                "something cloud-init=enabled else",
                status.UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE,
                "expected enabled cloud-init",
                "Cloud-init enabled by kernel command line cloud-init=enabled",
                id="false_on_kernel_cmdline_enable",
            ),
            # When kernel command line disables cloud-init return True.
            pytest.param(
                None,
                True,
                "something cloud-init=disabled else",
                status.UXAppBootStatusCode.DISABLED_BY_KERNEL_CMDLINE,
                "expected disabled cloud-init",
                "Cloud-init disabled by kernel parameter cloud-init=disabled",
                id="true_on_kernel_cmdline",
            ),
            # When cloud-init-generator writes disabled file return True.
            pytest.param(
                lambda config: os.path.join(config.paths.run_dir, "disabled"),
                True,
                "something",
                status.UXAppBootStatusCode.DISABLED_BY_GENERATOR,
                "expected disabled cloud-init",
                "Cloud-init disabled by cloud-init-generator",
                id="true_when_generator_disables",
            ),
            # Report enabled when systemd generator creates the enabled file.
            pytest.param(
                lambda config: os.path.join(config.paths.run_dir, "enabled"),
                True,
                "something ignored",
                status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
                "expected enabled cloud-init",
                "Cloud-init enabled by systemd cloud-init-generator",
                id="false_when_enabled_in_systemd",
            ),
        ],
    )
    def test_get_bootstatus(
        self,
        ensured_file: Optional[Callable],
        uses_systemd: bool,
        get_cmdline: str,
        expected_bootstatus: bool,
        failure_msg: str,
        expected_reason: Union[str, Callable],
        config: Config,
    ):
        if ensured_file is not None:
            ensure_file(ensured_file(config))
        (code, reason) = wrap_and_call(
            M_NAME,
            {
                "uses_systemd": uses_systemd,
                "get_cmdline": get_cmdline,
            },
            status.get_bootstatus,
            config.disable_file,
            config.paths,
        )
        assert code == expected_bootstatus, failure_msg
        if isinstance(expected_reason, str):
            assert reason == expected_reason
        else:
            assert reason == expected_reason(config)

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_returns_not_run(
        self, m_read_cfg_paths, config: Config, capsys
    ):
        """When status.json does not exist yet, return 'not run'."""
        m_read_cfg_paths.return_value = config.paths
        assert not os.path.exists(
            config.status_file
        ), "Unexpected status.json found"
        cmdargs = MyArgs(long=False, wait=False, format="tabular")
        retcode = wrap_and_call(
            M_NAME,
            {"get_bootstatus": (status.UXAppBootStatusCode.UNKNOWN, "")},
            status.handle_status_args,
            "ignored",
            cmdargs,
        )
        assert retcode == 0
        out, _err = capsys.readouterr()
        assert out == "status: not run\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_status_returns_disabled_long_on_presence_of_disable_file(
        self, m_read_cfg_paths, config: Config, capsys
    ):
        """When cloudinit is disabled, return disabled reason."""
        m_read_cfg_paths.return_value = config.paths
        checked_files = []

        def fakeexists(filepath):
            checked_files.append(filepath)
            status_file = os.path.join(config.paths.run_dir, "status.json")
            return bool(not filepath == status_file)

        cmdargs = MyArgs(long=True, wait=False, format="tabular")
        retcode = wrap_and_call(
            M_NAME,
            {
                "os.path.exists": {"side_effect": fakeexists},
                "get_bootstatus": (
                    status.UXAppBootStatusCode.DISABLED_BY_KERNEL_CMDLINE,
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
            boot_status_code: disabled-by-kernel-cmdline
            detail:
            disabled for some reason
        """
        )
        out, _err = capsys.readouterr()
        assert out == expected

    @pytest.mark.parametrize(
        [
            "ensured_file",
            "bootstatus",
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
                status.UXAppBootStatusCode.UNKNOWN,
                {},
                lambda config: config.result_file,
                MyArgs(long=False, wait=False, format="tabular"),
                0,
                "status: running\n",
                id="running_on_no_results_json",
            ),
            # Report running when status exists with an unfinished stage.
            pytest.param(
                lambda config: config.result_file,
                status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
                {"v1": {"init": {"start": 1, "finished": None}}},
                None,
                MyArgs(long=False, wait=False, format="tabular"),
                0,
                "status: running\n",
                id="running",
            ),
            # Report done results.json exists no stages are unfinished.
            pytest.param(
                lambda config: config.result_file,
                status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
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
                MyArgs(long=False, wait=False, format="tabular"),
                0,
                "status: done\n",
                id="done",
            ),
            # Long format of done status includes datasource info.
            pytest.param(
                lambda config: config.result_file,
                status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
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
                MyArgs(long=True, wait=False, format="tabular"),
                0,
                dedent(
                    """\
                    status: done
                    boot_status_code: enabled-by-generator
                    last_update: Thu, 01 Jan 1970 00:02:05 +0000
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
                status.UXAppBootStatusCode.ENABLED_BY_GENERATOR,
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
                MyArgs(long=False, wait=False, format="tabular"),
                1,
                "status: error\n",
                id="on_errors",
            ),
            # Long format of error status includes all error messages.
            pytest.param(
                None,
                status.UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE,
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
                MyArgs(long=True, wait=False, format="tabular"),
                1,
                dedent(
                    """\
                    status: error
                    boot_status_code: enabled-by-kernel-cmdline
                    last_update: Thu, 01 Jan 1970 00:02:05 +0000
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
                status.UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE,
                {
                    "v1": {
                        "stage": "init",
                        "init": {"start": 124.456, "finished": None},
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=True, wait=False, format="tabular"),
                0,
                dedent(
                    """\
                    status: running
                    boot_status_code: enabled-by-kernel-cmdline
                    last_update: Thu, 01 Jan 1970 00:02:04 +0000
                    detail:
                    Running in stage: init
                    """
                ),
                id="running_long_format",
            ),
            pytest.param(
                None,
                status.UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE,
                {
                    "v1": {
                        "stage": "init",
                        "init": {"start": 124.456, "finished": None},
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=False, wait=False, format="yaml"),
                0,
                dedent(
                    """\
                   ---
                   _schema_version: '1'
                   boot_status_code: enabled-by-kernel-cmdline
                   datasource: ''
                   detail: 'Running in stage: init'
                   errors: []
                   last_update: Thu, 01 Jan 1970 00:02:04 +0000
                   schemas:
                       '1':
                           boot_status_code: enabled-by-kernel-cmdline
                           datasource: ''
                           detail: 'Running in stage: init'
                           errors: []
                           last_update: Thu, 01 Jan 1970 00:02:04 +0000
                           status: running
                   status: running
                   ...

                   """
                ),
                id="running_yaml_format",
            ),
            pytest.param(
                None,
                status.UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE,
                {
                    "v1": {
                        "stage": "init",
                        "init": {"start": 124.456, "finished": None},
                        "init-local": {"start": 123.45, "finished": 123.46},
                    }
                },
                None,
                MyArgs(long=False, wait=False, format="json"),
                0,
                {
                    "_schema_version": "1",
                    "boot_status_code": "enabled-by-kernel-cmdline",
                    "datasource": "",
                    "detail": "Running in stage: init",
                    "errors": [],
                    "last_update": "Thu, 01 Jan 1970 00:02:04 +0000",
                    "schemas": {
                        "1": {
                            "boot_status_code": "enabled-by-kernel-cmdline",
                            "datasource": "",
                            "detail": "Running in stage: init",
                            "errors": [],
                            "last_update": "Thu, 01 Jan 1970 00:02:04 +0000",
                            "status": "running",
                        }
                    },
                    "status": "running",
                },
                id="running_json_format",
            ),
        ],
    )
    @mock.patch(M_PATH + "read_cfg_paths")
    @mock.patch(f"{M_PATH}_get_systemd_status", return_value=None)
    def test_status_output(
        self,
        m_get_systemd_status,
        m_read_cfg_paths,
        ensured_file: Optional[Callable],
        bootstatus: status.UXAppBootStatusCode,
        status_content: Dict,
        assert_file,
        cmdargs: MyArgs,
        expected_retcode: int,
        expected_status: str,
        config: Config,
        capsys,
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
        retcode = wrap_and_call(
            M_NAME,
            {"get_bootstatus": (bootstatus, "")},
            status.handle_status_args,
            "ignored",
            cmdargs,
        )
        assert retcode == expected_retcode
        out, _err = capsys.readouterr()
        if isinstance(expected_status, dict):
            assert json.loads(out) == expected_status
        else:
            assert out == expected_status

    @mock.patch(M_PATH + "read_cfg_paths")
    @mock.patch(f"{M_PATH}_get_systemd_status", return_value=None)
    def test_status_wait_blocks_until_done(
        self, m_get_systemd_status, m_read_cfg_paths, config: Config, capsys
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

        cmdargs = MyArgs(long=False, wait=True, format="tabular")
        retcode = wrap_and_call(
            M_NAME,
            {
                "sleep": {"side_effect": fake_sleep},
                "get_bootstatus": (status.UXAppBootStatusCode.UNKNOWN, ""),
            },
            status.handle_status_args,
            "ignored",
            cmdargs,
        )
        assert retcode == 0
        assert sleep_calls == 4
        out, _err = capsys.readouterr()
        assert out == "....\nstatus: done\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    @mock.patch(f"{M_PATH}_get_systemd_status", return_value=None)
    def test_status_wait_blocks_until_error(
        self, m_get_systemd_status, m_read_cfg_paths, config: Config, capsys
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

        cmdargs = MyArgs(long=False, wait=True, format="tabular")
        retcode = wrap_and_call(
            M_NAME,
            {
                "sleep": {"side_effect": fake_sleep},
                "get_bootstatus": (status.UXAppBootStatusCode.UNKNOWN, ""),
            },
            status.handle_status_args,
            "ignored",
            cmdargs,
        )
        assert retcode == 1
        assert sleep_calls == 4
        out, _err = capsys.readouterr()
        assert out == "....\nstatus: error\n"

    @mock.patch(M_PATH + "read_cfg_paths")
    @mock.patch(f"{M_PATH}_get_systemd_status", return_value=None)
    def test_status_main(
        self, m_get_systemd_status, m_read_cfg_paths, config: Config, capsys
    ):
        """status.main can be run as a standalone script."""
        m_read_cfg_paths.return_value = config.paths
        write_json(
            config.status_file,
            {"v1": {"init": {"start": 1, "finished": None}}},
        )
        with pytest.raises(SystemExit) as e:
            wrap_and_call(
                M_NAME,
                {
                    "sys.argv": {"new": ["status"]},
                    "get_bootstatus": (status.UXAppBootStatusCode.UNKNOWN, ""),
                },
                status.main,
            )
        assert e.value.code == 0
        out, _err = capsys.readouterr()
        assert out == "status: running\n"


class TestSystemdStatusDetails:
    @pytest.mark.parametrize(
        ["active_state", "unit_file_state", "sub_state", "status"],
        [
            # To cut down on the combination of states, I'm grouping
            # enabled, enabled-runtime, and static into an "enabled" state
            # and everything else functionally disabled.
            # Additionally, SubStates are undocumented and may mean something
            # different depending on the ActiveState they are mapped too.
            # Because of this I'm only testing SubState combinations seen
            # in real-world testing (or using "any" string if we dont care).
            ("activating", "enabled", "start", UXAppStatus.RUNNING),
            ("active", "enabled-runtime", "exited", None),
            # Dead doesn't mean exited here. It means not run yet.
            ("inactive", "static", "dead", UXAppStatus.RUNNING),
            ("reloading", "enabled", "start", UXAppStatus.RUNNING),
            ("deactivating", "enabled-runtime", "any", UXAppStatus.RUNNING),
            ("failed", "static", "failed", UXAppStatus.ERROR),
            # Try previous combinations again with "not enabled" states
            ("activating", "linked", "start", UXAppStatus.ERROR),
            ("active", "linked-runtime", "exited", UXAppStatus.ERROR),
            ("inactive", "masked", "dead", UXAppStatus.ERROR),
            ("reloading", "masked-runtime", "start", UXAppStatus.ERROR),
            ("deactivating", "disabled", "any", UXAppStatus.ERROR),
            ("failed", "invalid", "failed", UXAppStatus.ERROR),
        ],
    )
    def test_get_systemd_status(
        self, active_state, unit_file_state, sub_state, status
    ):
        with mock.patch(
            f"{M_PATH}subp.subp",
            return_value=SubpResult(
                f"ActiveState={active_state}\n"
                f"UnitFileState={unit_file_state}\n"
                f"SubState={sub_state}",
                stderr=None,
            ),
        ):
            assert _get_systemd_status() == status
