# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os

from cloudinit.config import cc_ubuntu_drivers as drivers
from cloudinit.config.schema import (
    SchemaValidationError,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

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


class AnyTempScriptAndDebconfFile(object):
    def __init__(self, tmp_dir, debconf_file):
        self.tmp_dir = tmp_dir
        self.debconf_file = debconf_file

    def __eq__(self, cmd):
        if not len(cmd) == 2:
            return False
        script, debconf_file = cmd
        if bool(script.startswith(self.tmp_dir) and script.endswith(".sh")):
            return debconf_file == self.debconf_file
        return False


class TestUbuntuDrivers(CiTestCase):
    cfg_accepted = {"drivers": {"nvidia": {"license-accepted": True}}}
    install_gpgpu = ["ubuntu-drivers", "install", "--gpgpu", "nvidia"]

    with_logs = True

    @skipUnlessJsonSchema()
    def test_schema_requires_boolean_for_license_accepted(self):
        with self.assertRaisesRegex(
            SchemaValidationError, ".*license-accepted.*TRUE.*boolean"
        ):
            validate_cloudconfig_schema(
                {"drivers": {"nvidia": {"license-accepted": "TRUE"}}},
                schema=drivers.schema,
                strict=True,
            )

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def _assert_happy_path_taken(self, config, m_which, m_subp, m_tmp):
        """Positive path test through handle. Package should be installed."""
        tdir = self.tmp_dir()
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()
        drivers.handle("ubuntu_drivers", config, myCloud, None, None)
        self.assertEqual(
            [mock.call(["ubuntu-drivers-common"])],
            myCloud.distro.install_packages.call_args_list,
        )
        self.assertEqual(
            [
                mock.call(AnyTempScriptAndDebconfFile(tdir, debconf_file)),
                mock.call(self.install_gpgpu),
            ],
            m_subp.call_args_list,
        )

    def test_handle_does_package_install(self):
        self._assert_happy_path_taken(self.cfg_accepted)

    def test_trueish_strings_are_considered_approval(self):
        for true_value in ["yes", "true", "on", "1"]:
            new_config = copy.deepcopy(self.cfg_accepted)
            new_config["drivers"]["nvidia"]["license-accepted"] = true_value
            self._assert_happy_path_taken(new_config)

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp")
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_handle_raises_error_if_no_drivers_found(
        self, m_which, m_subp, m_tmp
    ):
        """If ubuntu-drivers doesn't install any drivers, raise an error."""
        tdir = self.tmp_dir()
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()

        def fake_subp(cmd):
            if cmd[0].startswith(tdir):
                return
            raise ProcessExecutionError(
                stdout="No drivers found for installation.\n", exit_code=1
            )

        m_subp.side_effect = fake_subp

        with self.assertRaises(Exception):
            drivers.handle(
                "ubuntu_drivers", self.cfg_accepted, myCloud, None, None
            )
        self.assertEqual(
            [mock.call(["ubuntu-drivers-common"])],
            myCloud.distro.install_packages.call_args_list,
        )
        self.assertEqual(
            [
                mock.call(AnyTempScriptAndDebconfFile(tdir, debconf_file)),
                mock.call(self.install_gpgpu),
            ],
            m_subp.call_args_list,
        )
        self.assertIn(
            "ubuntu-drivers found no drivers for installation",
            self.logs.getvalue(),
        )

    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def _assert_inert_with_config(self, config, m_which, m_subp):
        """Helper to reduce repetition when testing negative cases"""
        myCloud = mock.MagicMock()
        drivers.handle("ubuntu_drivers", config, myCloud, None, None)
        self.assertEqual(0, myCloud.distro.install_packages.call_count)
        self.assertEqual(0, m_subp.call_count)

    def test_handle_inert_if_license_not_accepted(self):
        """Ensure we don't do anything if the license is rejected."""
        self._assert_inert_with_config(
            {"drivers": {"nvidia": {"license-accepted": False}}}
        )

    def test_handle_inert_if_garbage_in_license_field(self):
        """Ensure we don't do anything if unknown text is in license field."""
        self._assert_inert_with_config(
            {"drivers": {"nvidia": {"license-accepted": "garbage"}}}
        )

    def test_handle_inert_if_no_license_key(self):
        """Ensure we don't do anything if no license key."""
        self._assert_inert_with_config({"drivers": {"nvidia": {}}})

    def test_handle_inert_if_no_nvidia_key(self):
        """Ensure we don't do anything if other license accepted."""
        self._assert_inert_with_config(
            {"drivers": {"acme": {"license-accepted": True}}}
        )

    def test_handle_inert_if_string_given(self):
        """Ensure we don't do anything if string refusal given."""
        for false_value in ["no", "false", "off", "0"]:
            self._assert_inert_with_config(
                {"drivers": {"nvidia": {"license-accepted": false_value}}}
            )

    @mock.patch(MPATH + "install_drivers")
    def test_handle_no_drivers_does_nothing(self, m_install_drivers):
        """If no 'drivers' key in the config, nothing should be done."""
        myCloud = mock.MagicMock()
        myLog = mock.MagicMock()
        drivers.handle("ubuntu_drivers", {"foo": "bzr"}, myCloud, myLog, None)
        self.assertIn(
            "Skipping module named", myLog.debug.call_args_list[0][0][0]
        )
        self.assertEqual(0, m_install_drivers.call_count)

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=True)
    def test_install_drivers_no_install_if_present(
        self, m_which, m_subp, m_tmp
    ):
        """If 'ubuntu-drivers' is present, no package install should occur."""
        tdir = self.tmp_dir()
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        pkg_install = mock.MagicMock()
        drivers.install_drivers(
            self.cfg_accepted["drivers"], pkg_install_func=pkg_install
        )
        self.assertEqual(0, pkg_install.call_count)
        self.assertEqual([mock.call("ubuntu-drivers")], m_which.call_args_list)
        self.assertEqual(
            [
                mock.call(AnyTempScriptAndDebconfFile(tdir, debconf_file)),
                mock.call(self.install_gpgpu),
            ],
            m_subp.call_args_list,
        )

    def test_install_drivers_rejects_invalid_config(self):
        """install_drivers should raise TypeError if not given a config dict"""
        pkg_install = mock.MagicMock()
        with self.assertRaisesRegex(TypeError, ".*expected dict.*"):
            drivers.install_drivers("mystring", pkg_install_func=pkg_install)
        self.assertEqual(0, pkg_install.call_count)

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp")
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_install_drivers_handles_old_ubuntu_drivers_gracefully(
        self, m_which, m_subp, m_tmp
    ):
        """Older ubuntu-drivers versions should emit message and raise error"""
        tdir = self.tmp_dir()
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()

        def fake_subp(cmd):
            if cmd[0].startswith(tdir):
                return
            raise ProcessExecutionError(
                stderr=OLD_UBUNTU_DRIVERS_ERROR_STDERR, exit_code=2
            )

        m_subp.side_effect = fake_subp

        with self.assertRaises(Exception):
            drivers.handle(
                "ubuntu_drivers", self.cfg_accepted, myCloud, None, None
            )
        self.assertEqual(
            [mock.call(["ubuntu-drivers-common"])],
            myCloud.distro.install_packages.call_args_list,
        )
        self.assertEqual(
            [
                mock.call(AnyTempScriptAndDebconfFile(tdir, debconf_file)),
                mock.call(self.install_gpgpu),
            ],
            m_subp.call_args_list,
        )
        self.assertIn(
            "WARNING: the available version of ubuntu-drivers is"
            " too old to perform requested driver installation",
            self.logs.getvalue(),
        )


# Sub-class TestUbuntuDrivers to run the same test cases, but with a version
class TestUbuntuDriversWithVersion(TestUbuntuDrivers):
    cfg_accepted = {
        "drivers": {"nvidia": {"license-accepted": True, "version": "123"}}
    }
    install_gpgpu = ["ubuntu-drivers", "install", "--gpgpu", "nvidia:123"]

    @mock.patch(M_TMP_PATH)
    @mock.patch(MPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MPATH + "subp.which", return_value=False)
    def test_version_none_uses_latest(self, m_which, m_subp, m_tmp):
        tdir = self.tmp_dir()
        debconf_file = os.path.join(tdir, "nvidia.template")
        m_tmp.return_value = tdir
        myCloud = mock.MagicMock()
        version_none_cfg = {
            "drivers": {"nvidia": {"license-accepted": True, "version": None}}
        }
        drivers.handle("ubuntu_drivers", version_none_cfg, myCloud, None, None)
        self.assertEqual(
            [
                mock.call(AnyTempScriptAndDebconfFile(tdir, debconf_file)),
                mock.call(["ubuntu-drivers", "install", "--gpgpu", "nvidia"]),
            ],
            m_subp.call_args_list,
        )

    def test_specifying_a_version_doesnt_override_license_acceptance(self):
        self._assert_inert_with_config(
            {
                "drivers": {
                    "nvidia": {"license-accepted": False, "version": "123"}
                }
            }
        )


# vi: ts=4 expandtab
