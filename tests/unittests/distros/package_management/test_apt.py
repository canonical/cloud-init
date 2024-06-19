# This file is part of cloud-init. See LICENSE file for license information.
import tempfile
from itertools import count, cycle
from unittest import mock

import pytest

from cloudinit import helpers, subp
from cloudinit.distros.package_management import apt
from cloudinit.distros.package_management.apt import APT_GET_COMMAND, Apt
from tests.unittests.helpers import get_mock_paths
from tests.unittests.util import FakeDataSource

M_PATH = "cloudinit.distros.package_management.apt.Apt."
TMP_DIR = tempfile.TemporaryDirectory()


@mock.patch.dict("os.environ", {}, clear=True)
@mock.patch("cloudinit.distros.debian.subp.which", return_value=True)
@mock.patch("cloudinit.distros.debian.subp.subp")
class TestPackageCommand:
    @mock.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        return_value=True,
    )
    def test_simple_command(self, m_apt_avail, m_subp, m_which):
        apt = Apt(runner=mock.Mock(), apt_get_wrapper_command=["eatmydata"])
        apt.run_package_command("update")
        expected_call = {
            "args": ["eatmydata"] + list(APT_GET_COMMAND) + ["update"],
            "capture": False,
            "update_env": {"DEBIAN_FRONTEND": "noninteractive"},
        }
        assert m_subp.call_args == mock.call(**expected_call)

    @mock.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        side_effect=[False, False, True],
    )
    @mock.patch("cloudinit.distros.package_management.apt.time.sleep")
    def test_wait_for_lock(self, m_sleep, m_apt_avail, m_subp, m_which):
        apt = Apt(runner=mock.Mock(), apt_get_wrapper_command=("dontcare",))
        apt._wait_for_apt_command("stub", {"args": "stub2"})
        assert m_sleep.call_args_list == [mock.call(1), mock.call(1)]
        assert m_subp.call_args_list == [mock.call(args="stub2")]

    @mock.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        return_value=False,
    )
    @mock.patch("cloudinit.distros.package_management.apt.time.sleep")
    @mock.patch(
        "cloudinit.distros.package_management.apt.time.time",
        side_effect=count(),
    )
    def test_lock_wait_timeout(
        self, m_time, m_sleep, m_apt_avail, m_subp, m_which
    ):
        apt = Apt(runner=mock.Mock(), apt_get_wrapper_command=("dontcare",))
        with pytest.raises(TimeoutError):
            apt._wait_for_apt_command("stub", "stub2", timeout=5)
        assert m_subp.call_args_list == []

    @mock.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        side_effect=cycle([True, False]),
    )
    @mock.patch("cloudinit.distros.package_management.apt.time.sleep")
    def test_lock_exception_wait(self, m_sleep, m_apt_avail, m_subp, m_which):
        apt = Apt(runner=mock.Mock(), apt_get_wrapper_command=("dontcare",))
        exception = subp.ProcessExecutionError(
            exit_code=100, stderr="Could not get apt lock"
        )
        m_subp.side_effect = [exception, exception, "return_thing"]
        ret = apt._wait_for_apt_command("stub", {"args": "stub2"})
        assert ret == "return_thing"

    @mock.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        side_effect=cycle([True, False]),
    )
    @mock.patch("cloudinit.distros.package_management.apt.time.sleep")
    @mock.patch(
        "cloudinit.distros.package_management.apt.time.time",
        side_effect=count(),
    )
    def test_lock_exception_timeout(
        self, m_time, m_sleep, m_apt_avail, m_subp, m_which
    ):
        apt = Apt(runner=mock.Mock(), apt_get_wrapper_command=("dontcare",))
        m_subp.side_effect = subp.ProcessExecutionError(
            exit_code=100, stderr="Could not get apt lock"
        )
        with pytest.raises(TimeoutError):
            apt._wait_for_apt_command("stub", {"args": "stub2"}, timeout=5)

    def test_search_stem(self, m_subp, m_which, mocker):
        """Test that containing `-`, `^`, `/`, or `=` is handled correctly."""
        mocker.patch(f"{M_PATH}update_package_sources")
        mocker.patch(
            f"{M_PATH}get_all_packages",
            return_value=["cloud-init", "pkg2", "pkg3", "pkg4", "pkg5"],
        )
        m_install = mocker.patch(f"{M_PATH}run_package_command")

        apt = Apt(runner=mock.Mock())
        apt.install_packages(
            ["cloud-init", "pkg2-", "pkg3/jammy-updates", "pkg4=1.2", "pkg5^"]
        )
        m_install.assert_called_with(
            "install",
            pkgs=[
                "cloud-init",
                "pkg2-",
                "pkg3/jammy-updates",
                "pkg4=1.2",
                "pkg5^",
            ],
        )


@mock.patch.object(
    apt,
    "APT_LOCK_FILES",
    [f"{TMP_DIR}/{FILE}" for FILE in apt.APT_LOCK_FILES],
)
class TestUpdatePackageSources:
    def __init__(self):
        MockPaths = get_mock_paths(TMP_DIR)
        self.MockPaths = MockPaths({}, FakeDataSource())

    @mock.patch.object(apt.subp, "which", return_value=True)
    @mock.patch.object(apt.subp, "subp")
    def test_force_update_calls_twice(self, m_subp, m_which):
        """Ensure that force=true calls apt update again"""
        instance = apt.Apt(helpers.Runners(self.MockPaths))
        instance.update_package_sources()
        instance.update_package_sources(force=True)
        assert 2 == len(m_subp.call_args_list)
        TMP_DIR.cleanup()

    @mock.patch.object(apt.subp, "which", return_value=True)
    @mock.patch.object(apt.subp, "subp")
    def test_force_update_twice_calls_twice(self, m_subp, m_which):
        """Ensure that force=true calls apt update again when called twice"""
        instance = apt.Apt(helpers.Runners(self.MockPaths))
        instance.update_package_sources(force=True)
        instance.update_package_sources(force=True)
        assert 2 == len(m_subp.call_args_list)
        TMP_DIR.cleanup()

    @mock.patch.object(apt.subp, "which", return_value=True)
    @mock.patch.object(apt.subp, "subp")
    def test_no_force_update_calls_once(self, m_subp, m_which):
        """Ensure that apt-get update calls are deduped unless expected"""
        instance = apt.Apt(helpers.Runners(self.MockPaths))
        instance.update_package_sources()
        instance.update_package_sources()
        assert 1 == len(m_subp.call_args_list)
        TMP_DIR.cleanup()
