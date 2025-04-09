# This file is part of cloud-init. See LICENSE file for license information.

import pytest

import cloudinit.config.cc_raspberry_pi as cc_rpi
from cloudinit.config.cc_raspberry_pi import (
    ENABLE_RPI_CONNECT_KEY,
    RPI_BASE_KEY,
    RPI_INTERFACES_KEY,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_raspberry_pi."


class TestHandleRaspberryPi:
    @mock.patch(M_PATH + "configure_rpi_connect")
    def test_handle_rpi_connect_enabled(self, m_connect):
        cloud = get_cloud("raspberry-pi-os")
        cfg = {RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: True}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_connect.assert_called_once_with(True)

    @mock.patch(M_PATH + "configure_interface")
    def test_handle_configure_interface_i2c(self, m_iface):
        cloud = get_cloud("raspberry-pi-os")
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"i2c": True}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_iface.assert_called_once_with("i2c", True)

    @mock.patch(M_PATH + "configure_serial_interface")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_handle_configure_serial_interface_dict(self, m_ispi5, m_serial):
        cloud = get_cloud("raspberry-pi-os")
        serial_value = {
            "console": True,
            "hardware": True,
        }
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"serial": serial_value}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_serial.assert_called_once_with(serial_value, cfg)

    @mock.patch(M_PATH + "configure_serial_interface")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_handle_configure_serial_interface_bool(self, m_ispi5, m_serial):
        cloud = get_cloud("raspberry-pi-os")
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"serial": True}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_serial.assert_called_once_with(True, cfg)


@skipUnlessJsonSchema()
class TestRaspberryPiSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {"spi": True, "i2c": False}
                    }
                },
                None,
            ),
            (
                {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"spi": "true"}}},
                f"{RPI_BASE_KEY}.{RPI_INTERFACES_KEY}.spi: 'true' is not of type 'boolean'",
            ),
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {
                            "serial": {"console": True, "hardware": False}
                        }
                    }
                },
                None,
            ),
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {"serial": {"console": 123}}
                    }
                },
                f"{RPI_BASE_KEY}.{RPI_INTERFACES_KEY}.serial.console: 123 is not of type 'boolean'",
            ),
            ({RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: True}}, None),
            (
                {RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: "true"}},
                f"{RPI_BASE_KEY}.{ENABLE_RPI_CONNECT_KEY}: 'true' is not of type 'boolean'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
