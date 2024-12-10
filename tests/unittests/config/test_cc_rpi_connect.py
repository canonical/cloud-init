# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_rpi_connect import ENABLE_RPI_CONNECT_KEY
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
import pytest


"""
def is_notPi() -> bool:
    \"""Most tests are Raspberry Pi OS only.\"""
    return not os.path.exists("/etc/rpi-issue")

@mock.patch('cloudinit.subp.subp')
class TestCCRPiConnect(CiTestCase):
    \"""Tests work in progress. Just partially implemented to
    show the idea.\"""

    @mock.patch('cloudinit.subp.subp')
    def test_configure_rpi_connect_enabled(self, mock_subp):
        if is_notPi():
            return
        config = {ENABLE_RPI_CONNECT_KEY: True}
        handle("cc_rpi_connect", config, mock.Mock(), [])
        mock_subp.assert_called_with(
            ['/usr/bin/raspi-config', 'do_rpi_connect', '0'])

    @mock.patch('cloudinit.subp.subp')
    def test_configure_rpi_connect_disabled(self, mock_subp):
        if is_notPi():
            return
        config = {ENABLE_RPI_CONNECT_KEY: False}
        handle("cc_rpi_connect", config, mock.Mock(), [])
        mock_subp.assert_called_with(
            ['/usr/bin/raspi-config', 'do_rpi_connect', '1'])

    @mock.patch('os.path.exists')
    def test_rpi_connect_installed(self, mock_path_exists):
        if is_notPi():
            return
        # Simulate rpi-connect is installed
        mock_path_exists.return_value = True
        assert mock_path_exists('/usr/bin/rpi-connect')

    @mock.patch('os.path.exists')
    def test_rpi_connect_not_installed(self, mock_path_exists):
        if is_notPi():
            return
        # Simulate rpi-connect is not installed
        mock_path_exists.return_value = False
        assert not mock_path_exists('/usr/bin/rpi-connect')
"""


@skipUnlessJsonSchema()
class TestCCRPiConnectSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            ({ENABLE_RPI_CONNECT_KEY: True}, None),
            (
                {ENABLE_RPI_CONNECT_KEY: "true"},
                "'true' is not of type 'boolean'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
