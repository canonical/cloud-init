# This file is part of cloud-init. See LICENSE file for license information.
import logging
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.config.cc_package_update_upgrade_install import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.distros import PackageInstallerError
from cloudinit.subp import SubpResult
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud


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
            == "Failed to install packages: ['pkg1']"
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
            ({"packages": []}, "is too short"),
            (
                {"apt_update": False},
                (
                    "Cloud config schema deprecations: apt_update: "
                    "Default: ``false``. Deprecated in version 22.2. "
                    "Use ``package_update`` instead."
                ),
            ),
            (
                {"apt_upgrade": False},
                (
                    "Cloud config schema deprecations: apt_upgrade: "
                    "Default: ``false``. Deprecated in version 22.2. "
                    "Use ``package_upgrade`` instead."
                ),
            ),
            (
                {"apt_reboot_if_required": False},
                (
                    "Cloud config schema deprecations: "
                    "apt_reboot_if_required: Default: ``false``. "
                    "Deprecated in version 22.2. Use "
                    "``package_reboot_if_required`` instead."
                ),
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
