# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_rpi_userdata import (
    DISABLE_PIWIZ_KEY,
    RPI_USERCONF_KEY,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
import pytest
from tests.unittests.helpers import skipUnlessJsonSchema

"""
def is_notPi() -> bool:
    \"""Most tests are Raspberry Pi OS only.\"""
    return not os.path.exists("/etc/rpi-issue")

@mock.patch('cloudinit.subp.subp')
class TestCCRPiUserdata(CiTestCase):
    \"""Tests work in progress. Just partially implemented
    to show the idea.\"""

    @mock.patch('subprocess.run')
    def test_userconf_service_runs(self, mock_run):
        if is_notPi():
            return
        mock_run.return_value.returncode = 0
        result = run_service('hashedpassword', 'newuser')
        assert result is True

    @mock.patch('subprocess.run')
    def test_userconf_service_fails(self, mock_run):
        if is_notPi():
            return
        mock_run.return_value.returncode = 1
        result = run_service('hashedpassword', 'newuser')
        assert result is False

    @mock.patch('os.path.exists')
    def test_check_piwiz_disabled(self, mock_path_exists):
        if is_notPi():
            return
        mock_path_exists.side_effect = [False, False, False]
        assert not mock_path_exists('/var/lib/userconf-pi/autologin')
        assert not mock_path_exists('/etc/ssh/sshd_config.d/rename_user.conf')
        assert not mock_path_exists('/etc/xdg/autostart/piwiz.desktop')

    @mock.patch('os.listdir')
    def test_check_default_user_renamed(self, mock_listdir):
        if is_notPi():
            return
        mock_listdir.return_value = ['newuser']
        assert 'newuser' in os.listdir('/home')

    @mock.patch('os.listdir')
    def test_default_user_still_exists(self, mock_listdir):
        if is_notPi():
            return
        mock_listdir.return_value = ['pi']
        assert 'pi' in os.listdir('/home')
"""


@skipUnlessJsonSchema()
class TestCCRPiUserdataSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            ({DISABLE_PIWIZ_KEY: True}, None),
            (
                {
                    RPI_USERCONF_KEY: {
                        "password": "hashedpassword",
                        "user": "newuser",
                    }
                },
                None,
            ),
            ({DISABLE_PIWIZ_KEY: "true"}, "'true' is not of type 'boolean'"),
            (
                {RPI_USERCONF_KEY: {"password": 12345}},
                "12345 is not of type 'string'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
