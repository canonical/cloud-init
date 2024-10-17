# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_rpi_interfaces import RPI_INTERFACES_KEY
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
class TestCCRPiInterfaces(CiTestCase):
    \"""Tests work in progress. Just partially implemented to
     show the idea.\"""

    @mock.patch('cloudinit.subp.subp')
    def test_configure_spi_interface(self, mock_subp):
        if is_notPi():
            return
        config = {
            RPI_INTERFACES_KEY: {
                "spi": True
            }
        }
        handle("cc_rpi_interfaces", config, mock.Mock(), [])
        mock_subp.assert_called_with([
            '/usr/bin/raspi-config',
            'nonint',
            SUPPORTED_INTERFACES["spi"],
            '0'])

    @mock.patch('cloudinit.subp.subp')
    def test_configure_serial_interface_as_dict(self, mock_subp):
        if is_notPi():
            return
        config = {
            RPI_INTERFACES_KEY: {
                "serial": {
                    "console": True,
                    "hardware": False
                }
            }
        }
        handle("cc_rpi_interfaces", config, mock.Mock(), [])
        mock_subp.assert_any_call([
            '/usr/bin/raspi-config', 'nonint', 'do_serial_cons', '0'])

    @mock.patch('cloudinit.subp.subp')
    def test_configure_invalid_interface(self, mock_subp):
        if is_notPi():
            return
        config = {
            RPI_INTERFACES_KEY: {
                "unknown_interface": True
            }
        }
        handle("cc_rpi_interfaces", config, mock.Mock(), [])
        mock_subp.assert_not_called()

    @mock.patch('os.path.exists')
    @mock.patch('cloudinit.subp.subp')
    def test_get_enabled_interfaces(self, mock_subp, mock_path_exists):
        if is_notPi():
            return
        # Simulate all interfaces enabled (spi, i2c, etc.)
        mock_subp.side_effect = [("0", ""), ("0", ""), ("0", ""), ("0", "")]
        config = {
            RPI_INTERFACES_KEY: {
                "spi": True,
                "i2c": True,
                "onewire": True,
                "remote_gpio": True
            }
        }
        handle("cc_rpi_interfaces", config, mock.Mock(), [])
        # Assert all interface enabling commands were called
        mock_subp.assert_any_call(['/usr/bin/raspi-config',
        'nonint', 'do_spi', '0'])
        mock_subp.assert_any_call(['/usr/bin/raspi-config',
        'nonint', 'do_i2c', '0'])
        mock_subp.assert_any_call(['/usr/bin/raspi-config',
        'nonint', 'do_onewire', '0'])
        mock_subp.assert_any_call(['/usr/bin/raspi-config',
        'nonint', 'do_rgpio', '0'])
"""


@skipUnlessJsonSchema()
class TestCCRPiInterfacesSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            ({RPI_INTERFACES_KEY: {"spi": True, "i2c": False}}, None),
            (
                {RPI_INTERFACES_KEY: {"spi": "true"}},
                "'true' is not of type 'boolean'",
            ),
            (
                {
                    RPI_INTERFACES_KEY: {
                        "serial": {"console": True, "hardware": False}
                    }
                },
                None,
            ),
            (
                {RPI_INTERFACES_KEY: {"serial": {"console": 123}}},
                "123 is not of type 'boolean'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
