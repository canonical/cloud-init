# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
import os
import re

import pytest

from cloudinit.config import cc_ubuntu_drivers as drivers
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import mock, skipUnlessJsonSchema

MPATH = "cloudinit.config.cc_ubuntu_drivers."
M_TMP_PATH = MPATH + "temp_utils.mkdtemp"
OLD_UBUNTU_DRIVERS_ERROR_STDERR = (
    "ubuntu-drivers: error: argument <command>: invalid choice: 'install' "
    "(choose from 'list', 'autoinstall', 'devices', 'debug')\n"
)


# The tests in this module call helper methods which are decorated with
# mock.patch.  pylint doesn't understand that mock.patch passes parameters to
# the decorated function, so it incorrectly reports that we aren't passing
# values for all parameters.  Instead of annotating every single call, we
# disable it for the entire module:
#  pylint: disable=no-value-for-parameter


@pytest.mark.parametrize(
    "cfg_accepted,install_gpgpu",
    [
        pytest.param(
            {"drivers": {"nvidia": {"license-accepted": True}}},
            ["ubuntu-drivers", "install", "--gpgpu", "nvidia"],
            id="without_version",
        ),
        pytest.param(
            {
                "drivers": {
                    "nvidia": {"license-accepted": True, "version": "123"}
                }
            },
            ["ubuntu-drivers", "install", "--gpgpu", "nvidia:123"],
            id="with_version",
        ),
    ],
)
@mock.patch(MPATH + "debconf")
@mock.patch(MPATH + "HAS_DEBCONF", True)
class TestUbuntuDrivers:
    install_gpgpu = ["ubuntu-drivers", "install", "--gpgpu", "nvidia"]

    @pytest.mark.parametrize(
        "true_value",
        [
            True,
            "yes",
            "true",
            "on",
            "1",
        ],
    )
    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_happy_path_taken(
        self,
        m_which,
        m_subp,
        m_tmp,
        m_debconf,
        tmpdir,
        cfg_accepted,
        install_gpgpu,
        true_value,
    ):
        """Positive path test through handle. Package should be installed."""
        new_config: dict = copy.deepcopy(cfg_accepted)
        new_config["drivers"]["nvidia"]["license-accepted"] = true_value

        tdir = tmpdir
        debconf_file = tdir.join("nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()
        drivers.handle("ubuntu_drivers", new_config, myCloud, None)
        assert [
            mock.call(drivers.X_LOADTEMPLATEFILE, debconf_file)
        ] == m_debconf.DebconfCommunicator().__enter__().command.call_args_list
        assert [
            mock.call(["ubuntu-drivers-common"])
        ] == myCloud.distro.install_packages.call_args_list
        assert [mock.call(install_gpgpu)] == m_subp.call_args_list

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp")
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_handle_raises_error_if_no_drivers_found(
        self,
        m_which,
        m_subp,
        m_tmp,
        m_debconf,
        caplog,
        tmpdir,
        cfg_accepted,
        install_gpgpu,
    ):
        """If ubuntu-drivers doesn't install any drivers, raise an error."""
        tdir = tmpdir
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()

        m_subp.side_effect = ProcessExecutionError(
            stdout="No drivers found for installation.\n", exit_code=1
        )

        with pytest.raises(Exception):
            drivers.handle("ubuntu_drivers", cfg_accepted, myCloud, None)
        assert [
            mock.call(drivers.X_LOADTEMPLATEFILE, debconf_file)
        ] == m_debconf.DebconfCommunicator().__enter__().command.call_args_list
        assert [
            mock.call(["ubuntu-drivers-common"])
        ] == myCloud.distro.install_packages.call_args_list
        assert [mock.call(install_gpgpu)] == m_subp.call_args_list
        assert (
            "ubuntu-drivers found no drivers for installation" in caplog.text
        )

    @pytest.mark.parametrize(
        "config",
        [
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": False}}},
                id="license_not_accepted",
            ),
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": "garbage"}}},
                id="garbage_in_license_field",
            ),
            pytest.param({"drivers": {"nvidia": {}}}, id="no_license_key"),
            pytest.param(
                {"drivers": {"acme": {"license-accepted": True}}},
                id="no_nvidia_key",
            ),
            # ensure we don't do anything if string refusal given
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": "no"}}},
                id="string_given_no",
            ),
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": "false"}}},
                id="string_given_false",
            ),
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": "off"}}},
                id="string_given_off",
            ),
            pytest.param(
                {"drivers": {"nvidia": {"license-accepted": "0"}}},
                id="string_given_0",
            ),
            # specifying_a_version_doesnt_override_license_acceptance
            pytest.param(
                {
                    "drivers": {
                        "nvidia": {"license-accepted": False, "version": "123"}
                    }
                },
                id="with_version",
            ),
        ],
    )
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_handle_inert(
        self, m_which, m_subp, m_debconf, cfg_accepted, install_gpgpu, config
    ):
        """Helper to reduce repetition when testing negative cases"""
        myCloud = mock.MagicMock()
        drivers.handle("ubuntu_drivers", config, myCloud, None)
        assert 0 == myCloud.distro.install_packages.call_count
        assert 0 == m_subp.call_count

    @mock.patch(MPATH + "install_drivers")
    @mock.patch(MPATH + "LOG")
    def test_handle_no_drivers_does_nothing(
        self, m_log, m_install_drivers, m_debconf, cfg_accepted, install_gpgpu
    ):
        """If no 'drivers' key in the config, nothing should be done."""
        myCloud = mock.MagicMock()
        drivers.handle("ubuntu_drivers", {"foo": "bzr"}, myCloud, None)
        assert "Skipping module named" in m_log.debug.call_args_list[0][0][0]
        assert 0 == m_install_drivers.call_count

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=True)
    def test_install_drivers_no_install_if_present(
        self,
        m_which,
        m_subp,
        m_tmp,
        m_debconf,
        tmpdir,
        cfg_accepted,
        install_gpgpu,
    ):
        """If 'ubuntu-drivers' is present, no package install should occur."""
        tdir = tmpdir
        debconf_file = tmpdir.join("nvidia.template")
        m_tmp.return_value = tdir
        pkg_install = mock.MagicMock()
        distro = mock.Mock()
        drivers.install_drivers(
            cfg_accepted["drivers"],
            pkg_install_func=pkg_install,
            distro=distro,
        )
        assert 0 == pkg_install.call_count
        assert [mock.call("ubuntu-drivers")] == m_which.call_args_list
        assert [
            mock.call(drivers.X_LOADTEMPLATEFILE, debconf_file)
        ] == m_debconf.DebconfCommunicator().__enter__().command.call_args_list
        assert [mock.call(install_gpgpu)] == m_subp.call_args_list

    def test_install_drivers_rejects_invalid_config(
        self, m_debconf, cfg_accepted, install_gpgpu
    ):
        """install_drivers should raise TypeError if not given a config dict"""
        pkg_install = mock.MagicMock()
        distro = mock.Mock()
        with pytest.raises(TypeError, match=".*expected dict.*"):
            drivers.install_drivers(
                "mystring", pkg_install_func=pkg_install, distro=distro
            )
        assert 0 == pkg_install.call_count

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp")
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_install_drivers_handles_old_ubuntu_drivers_gracefully(
        self,
        m_which,
        m_subp,
        m_tmp,
        m_debconf,
        caplog,
        tmpdir,
        cfg_accepted,
        install_gpgpu,
    ):
        """Older ubuntu-drivers versions should emit message and raise error"""
        debconf_file = tmpdir.join("nvidia.template")
        m_tmp.return_value = tmpdir
        myCloud = mock.MagicMock()

        m_subp.side_effect = ProcessExecutionError(
            stderr=OLD_UBUNTU_DRIVERS_ERROR_STDERR, exit_code=2
        )

        with pytest.raises(Exception):
            drivers.handle("ubuntu_drivers", cfg_accepted, myCloud, None)
        assert [
            mock.call(drivers.X_LOADTEMPLATEFILE, debconf_file)
        ] == m_debconf.DebconfCommunicator().__enter__().command.call_args_list
        assert [
            mock.call(["ubuntu-drivers-common"])
        ] == myCloud.distro.install_packages.call_args_list
        assert [mock.call(install_gpgpu)] == m_subp.call_args_list
        assert (
            MPATH[:-1],
            logging.WARNING,
            (
                "the available version of ubuntu-drivers is"
                " too old to perform requested driver installation"
            ),
        ) == caplog.record_tuples[-1]

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_debconf_not_installed_does_nothing(
        self,
        m_which,
        m_subp,
        m_tmp,
        m_debconf,
        tmpdir,
        cfg_accepted,
        install_gpgpu,
    ):
        m_debconf.DebconfCommunicator.side_effect = AttributeError
        m_tmp.return_value = tmpdir
        myCloud = mock.MagicMock()
        version_none_cfg = {
            "drivers": {"nvidia": {"license-accepted": True, "version": None}}
        }
        with pytest.raises(AttributeError):
            drivers.handle("ubuntu_drivers", version_none_cfg, myCloud, None)
        assert (
            0 == m_debconf.DebconfCommunicator.__enter__().command.call_count
        )
        assert 0 == m_subp.call_count


@mock.patch(MPATH + "debconf")
@mock.patch(MPATH + "HAS_DEBCONF", True)
class TestUbuntuDriversWithVersion:
    """With-version specific tests"""

    cfg_accepted = {
        "drivers": {"nvidia": {"license-accepted": True, "version": "123"}}
    }
    install_gpgpu = ["ubuntu-drivers", "install", "--gpgpu", "nvidia:123"]

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_version_none_uses_latest(
        self, m_which, m_subp, m_tmp, m_debconf, tmpdir
    ):
        debconf_file = tmpdir.join("nvidia.template")
        m_tmp.return_value = tmpdir
        myCloud = mock.MagicMock()
        version_none_cfg = {
            "drivers": {"nvidia": {"license-accepted": True, "version": None}}
        }
        drivers.handle("ubuntu_drivers", version_none_cfg, myCloud, None)
        assert [
            mock.call(drivers.X_LOADTEMPLATEFILE, debconf_file)
        ] == m_debconf.DebconfCommunicator().__enter__().command.call_args_list
        assert [
            mock.call(["ubuntu-drivers", "install", "--gpgpu", "nvidia"]),
        ] == m_subp.call_args_list


@mock.patch(MPATH + "debconf")
class TestUbuntuDriversNotRun:
    @mock.patch(MPATH + "HAS_DEBCONF", True)
    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "install_drivers")
    @mock.patch(MPATH + "LOG")
    def test_no_cfg_drivers_does_nothing(
        self,
        m_log,
        m_install_drivers,
        m_tmp,
        m_debconf,
        tmpdir,
    ):
        m_tmp.return_value = tmpdir
        myCloud = mock.MagicMock()
        version_none_cfg = {}
        drivers.handle("ubuntu_drivers", version_none_cfg, myCloud, None)
        assert 0 == m_install_drivers.call_count
        assert (
            mock.call(
                "Skipping module named %s, no 'drivers' key in config",
                "ubuntu_drivers",
            )
            == m_log.debug.call_args_list[-1]
        )

    @mock.patch(MPATH + "HAS_DEBCONF", False)
    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "install_drivers")
    @mock.patch(MPATH + "LOG")
    def test_has_not_debconf_does_nothing(
        self,
        m_log,
        m_install_drivers,
        m_tmp,
        m_debconf,
        tmpdir,
    ):
        m_tmp.return_value = tmpdir
        myCloud = mock.MagicMock()
        version_none_cfg = {"drivers": {"nvidia": {"license-accepted": True}}}
        drivers.handle("ubuntu_drivers", version_none_cfg, myCloud, None)
        assert 0 == m_install_drivers.call_count
        assert (
            mock.call(
                "Skipping module named %s, 'python3-debconf' is not installed",
                "ubuntu_drivers",
            )
            == m_log.warning.call_args_list[-1]
        )


class TestUbuntuAdvantageSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Strict boolean license-accepted
            (
                {"drivers": {"nvidia": {"license-accepted": "TRUE"}}},
                "drivers.nvidia.license-accepted: 'TRUE' is not of type"
                " 'boolean'",
            ),
            # Additional properties disallowed
            (
                {"drivers": {"bogus": {"license-accepted": True}}},
                re.escape(
                    "drivers: Additional properties are not allowed ('bogus'"
                ),
            ),
            (
                {"drivers": {"nvidia": {"bogus": True}}},
                re.escape(
                    "drivers.nvidia: Additional properties are not allowed"
                    " ('bogus' "
                ),
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
