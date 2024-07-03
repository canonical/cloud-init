# This file is part of cloud-init. See LICENSE file for license information.
import logging
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.config.cc_package_update_upgrade_install import (
    REBOOT_FILES,
    handle,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.distros import PackageInstallerError
from cloudinit.subp import SubpResult
from tests.unittests.helpers import (
    SCHEMA_EMPTY_ERROR,
    does_not_raise,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_package_update_upgrade_install."


@pytest.fixture
def common_mocks(mocker):
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch("cloudinit.distros.Distro.update_package_sources")
    mocker.patch(
        "cloudinit.distros.package_management.apt.Apt.update_package_sources"
    )
    mocker.patch(
        "cloudinit.distros.package_management.apt.Apt._apt_lock_available",
        return_value=True,
    )
    mocker.patch(
        "cloudinit.distros.package_management.apt.Apt.available",
        return_value=True,
    )
    mocker.patch(
        "cloudinit.distros.package_management.snap.Snap.available",
        return_value=True,
    )


class TestRebootIfRequired:
    @pytest.mark.parametrize(
        "cloud_cfg,reboot_file,expectation",
        (
            pytest.param(
                {"package_reboot_if_required": True},
                "/run/reboot-needed",
                does_not_raise(),
                id="no_reboot_when_no_package_changes",
            ),
            pytest.param(
                {"package_reboot_if_required": True, "package_upgrade": True},
                "/run/reboot-needed",
                pytest.raises(
                    RuntimeError
                ),  # _fire_reboot raises RuntimeError
                id="perform_reboot_on_package_upgrade_and_suse_reboot_marker",
            ),
            pytest.param(
                {"package_reboot_if_required": True, "package_upgrade": True},
                "",  # No reboot-needed flag file present
                does_not_raise(),
                id="no_reboot_on_package_upgrade_and_no_reboot_required_file",
            ),
            pytest.param(
                {"package_reboot_if_required": True, "package_upgrade": True},
                "/var/run/reboot-required",
                pytest.raises(
                    RuntimeError
                ),  # _fire_reboot raises RuntimeError
                id="perform_reboot_on_package_upgrade_and_reboot_marker",
            ),
            pytest.param(
                {"package_reboot_if_required": True, "packages": ["sl"]},
                "/var/run/reboot-required",
                pytest.raises(
                    RuntimeError
                ),  # _fire_reboot raises RuntimeError
                id="perform_reboot_on_packages_and_reboot_marker",
            ),
        ),
    )
    def test_wb_only_reboot_on_reboot_when_configured_and_required(
        self, cloud_cfg, reboot_file, expectation, common_mocks, caplog
    ):
        """Only reboot when packages are updated and reboot_if_required.

        Whitebox testing because _fire_reboot will not actually reboot the
        system and we expect to fallback to a raised RuntimeError in testing

        NOOP when any of the following are not true:
          - no reboot_if_requred: true config
          - no reboot-required flag files exist
          - no packages were changed by cloud-init via upgrade or packages cfg
        """

        def _isfile(filename: str):
            return filename == reboot_file

        cloud = get_cloud("ubuntu")

        subp_call = None
        sleep_count = 0
        if cloud_cfg.get("package_reboot_if_required"):
            if reboot_file in REBOOT_FILES:
                if cloud_cfg.get("package_upgrade") or cloud_cfg.get(
                    "packages"
                ):
                    sleep_count = 6
                    # Expect a RuntimeError after sleeps because of mocked
                    # subp and not really rebooting the system
                    subp_call = ["/sbin/reboot"]

        caplog.set_level(logging.WARNING)
        with mock.patch(
            "cloudinit.subp.subp", return_value=("fakeout", "fakeerr")
        ) as m_subp:
            with mock.patch("os.path.isfile", side_effect=_isfile):
                with mock.patch(M_PATH + "time.sleep") as m_sleep:
                    with mock.patch(M_PATH + "flush_loggers"):
                        with expectation:
                            handle("", cloud_cfg, cloud, [])
        assert sleep_count == m_sleep.call_count
        if subp_call:
            assert (
                f"Rebooting after upgrade or install per {reboot_file}"
                in caplog.text
            )
            m_subp.assert_called_with(subp_call)


class TestMultiplePackageManagers:
    def test_explicit_apt(self, common_mocks):
        def _new_subp(*args, **kwargs):
            if args and "apt-cache" in args[0]:
                return SubpResult("pkg1\npkg2\npkg3", None)

        cloud = get_cloud("ubuntu")
        cfg = {"packages": [{"apt": ["pkg1", "pkg2"]}]}
        with mock.patch(
            "cloudinit.subp.subp", side_effect=_new_subp
        ) as m_subp:
            handle("", cfg, cloud, [])

        assert len(m_subp.call_args_list) == 2
        assert m_subp.call_args_list[0] == mock.call(["apt-cache", "pkgnames"])

        for arg in ["apt-get", "install", "pkg1", "pkg2"]:
            assert arg in m_subp.call_args_list[1][1]["args"]

    def test_explicit_apt_version(self, common_mocks):
        def _new_subp(*args, **kwargs):
            if args and "apt-cache" in args[0]:
                return SubpResult("pkg1\npkg2\npkg3", None)

        cloud = get_cloud("ubuntu")
        cfg = {"packages": [{"apt": ["pkg1", ["pkg2", "1.2.3"]]}]}
        with mock.patch(
            "cloudinit.subp.subp", side_effect=_new_subp
        ) as m_subp:
            handle("", cfg, cloud, [])

        assert len(m_subp.call_args_list) == 2
        assert m_subp.call_args_list[0] == mock.call(["apt-cache", "pkgnames"])

        for arg in ["apt-get", "install", "pkg1", "pkg2=1.2.3"]:
            assert arg in m_subp.call_args_list[1][1]["args"]

    @mock.patch("cloudinit.subp.subp")
    def test_explicit_snap(self, m_subp, common_mocks):
        cloud = get_cloud("ubuntu")
        cfg = {"packages": [{"snap": ["pkg1", "pkg2"]}]}
        handle("", cfg, cloud, [])

        assert len(m_subp.call_args_list) == 2
        assert mock.call(["snap", "install", "pkg1"]) in m_subp.call_args_list
        assert mock.call(["snap", "install", "pkg2"]) in m_subp.call_args_list

    @mock.patch("cloudinit.subp.subp")
    def test_explicit_snap_version(self, m_subp, common_mocks):
        cloud = get_cloud("ubuntu")
        cfg = {"packages": [{"snap": ["pkg1", ["pkg2", "--edge"]]}]}
        handle("", cfg, cloud, [])

        assert len(m_subp.call_args_list) == 2
        assert mock.call(["snap", "install", "pkg1"]) in m_subp.call_args_list
        assert (
            mock.call(["snap", "install", "pkg2", "--edge"])
            in m_subp.call_args_list
        )

    def test_combined(self, common_mocks):
        """Ensure that pkg1 is installed by snap since it isn't available
        in the apt cache, and ensure pkg5 is installed by snap even though it
        is available under apt because it is explicitly listed under snap."""

        def _new_subp(*args, **kwargs):
            if args and "apt-cache" in args[0]:
                return SubpResult("pkg2\npkg3\npkg5\npkg6", None)

        cloud = get_cloud("ubuntu")
        cfg = {
            "packages": [
                "pkg1",
                {"apt": ["pkg2", ["pkg3", "1.2.3"]]},
                {"snap": ["pkg4", ["pkg5", "--edge"]]},
                "pkg6",
            ],
        }
        with mock.patch(
            "cloudinit.subp.subp", side_effect=_new_subp
        ) as m_subp:
            handle("", cfg, cloud, [])

        assert len(m_subp.call_args_list) == 5
        assert m_subp.call_args_list[0] == mock.call(["apt-cache", "pkgnames"])
        for arg in ["apt-get", "install", "pkg2", "pkg3=1.2.3", "pkg6"]:
            assert arg in m_subp.call_args_list[1][1]["args"]

        assert mock.call(["snap", "install", "pkg1"]) in m_subp.call_args_list
        assert (
            mock.call(["snap", "install", "pkg5", "--edge"])
            in m_subp.call_args_list
        )
        assert mock.call(["snap", "install", "pkg4"]) in m_subp.call_args_list

    def test_error_apt(self, common_mocks):
        """Since we have already checked that the package(s) exists in apt,
        if we have an error in apt, we don't want to fall through to
        additional package installs.
        """

        def _new_subp(*args, **kwargs):
            if args and "apt-cache" in args[0]:
                return SubpResult("pkg1", None)
            if "args" in kwargs and "install" in kwargs["args"]:
                raise subp.ProcessExecutionError(
                    cmd=kwargs["args"],
                    stdout="dontcare",
                    stderr="E: Unable to locate package pkg1",
                    exit_code=100,
                )

        cloud = get_cloud("ubuntu")
        cfg = {"packages": ["pkg1"]}
        with mock.patch("cloudinit.subp.subp", side_effect=_new_subp):
            with pytest.raises(subp.ProcessExecutionError):
                handle("", cfg, cloud, [])

    def test_error_snap(self, common_mocks, caplog):
        """Since we haven't checked the package(s) existence, we should fall
        through to additional package installs.
        """
        caplog.set_level(logging.DEBUG)

        def _new_subp(*args, **kwargs):
            if args:
                if "apt-cache" in args[0]:
                    return SubpResult("", None)
                if "install" in args[0]:
                    raise subp.ProcessExecutionError(
                        cmd=args[0],
                        stdout="dontcare",
                        stderr='error: snap "pkg1" not found',
                        exit_code=1,
                    )

        cloud = get_cloud("ubuntu")
        cfg = {"packages": ["pkg1"]}
        with mock.patch("cloudinit.subp.subp", side_effect=_new_subp):
            with pytest.raises(PackageInstallerError):
                handle("", cfg, cloud, [])

        assert caplog.records[-3].levelname == "WARNING"
        assert (
            caplog.records[-3].message
            == "Failure when attempting to install packages: ['pkg1']"
        )


class TestPackageUpdateUpgradeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # packages list with single entry (2 required)
            ({"packages": ["p1", ["p2"]]}, ""),
            # packages list with three entries (2 required)
            ({"packages": ["p1", ["p2", "p3", "p4"]]}, ""),
            # empty packages list
            ({"packages": []}, SCHEMA_EMPTY_ERROR),
            (
                {"apt_update": False},
                (
                    "Cloud config schema deprecations: apt_update:  "
                    "Deprecated in version 22.2. "
                    "Use ``package_update`` instead."
                ),
            ),
            (
                {"apt_upgrade": False},
                (
                    "Cloud config schema deprecations: apt_upgrade:  "
                    "Deprecated in version 22.2. "
                    "Use ``package_upgrade`` instead."
                ),
            ),
            (
                {"apt_reboot_if_required": False},
                (
                    "Cloud config schema deprecations: "
                    "apt_reboot_if_required:  Deprecated in version 22.2. Use "
                    "``package_reboot_if_required`` instead."
                ),
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
