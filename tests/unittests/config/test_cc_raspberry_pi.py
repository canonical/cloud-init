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
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_raspberry_pi."


class TestHandleRaspberryPi:
    @mock.patch(M_PATH + "configure_rpi_connect")
    def test_handle_rpi_connect_enabled(self, m_connect):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: True}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_connect.assert_called_once_with(True)

    @mock.patch(M_PATH + "configure_interface")
    def test_handle_configure_interface_i2c(self, m_iface):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"i2c": True}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_iface.assert_called_once_with("i2c", True)

    @mock.patch(M_PATH + "configure_serial_interface")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_handle_configure_serial_interface_dict(self, m_ispi5, m_serial):
        cloud = get_cloud("raspberry_pi_os")
        serial_value = {
            "console": True,
            "hardware": True,
        }
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"serial": serial_value}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_serial.assert_called_once_with(serial_value, cfg, cloud)

    @mock.patch(M_PATH + "configure_serial_interface")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_handle_configure_serial_interface_bool(self, m_ispi5, m_serial):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"serial": True}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_serial.assert_called_once_with(True, cfg, cloud)


class TestRaspberryPiMethods:
    @mock.patch("cloudinit.subp.subp")
    def test_configure_rpi_connect_enable(self, m_subp):
        cc_rpi.configure_rpi_connect(True)
        m_subp.assert_called_once_with(
            ["/usr/bin/raspi-config", "do_rpi_connect", "0"]
        )

    @mock.patch(
        "cloudinit.subp.subp",
        side_effect=ProcessExecutionError("1", [], "fail"),
    )
    def test_configure_rpi_connect_failure(self, m_subp):
        cc_rpi.configure_rpi_connect(False)  # Should log error but not raise

    @mock.patch("cloudinit.subp.subp", return_value=("ok", ""))
    def test_is_pifive_true(self, m_subp):
        assert cc_rpi.is_pifive() is True

    @mock.patch(
        "cloudinit.subp.subp",
        side_effect=ProcessExecutionError("1", [], "fail"),
    )
    def test_is_pifive_false(self, m_subp):
        assert cc_rpi.is_pifive() is False

    @mock.patch("cloudinit.subp.subp")
    def test_configure_interface_valid(self, m_subp):
        cc_rpi.configure_interface("i2c", True)
        m_subp.assert_called_once_with(
            ["/usr/bin/raspi-config", "nonint", "do_i2c", "0"]
        )

    def test_configure_interface_invalid(self):
        with pytest.raises(AssertionError):
            cc_rpi.configure_interface("invalid_iface", True)

    @mock.patch("cloudinit.subp.subp")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_configure_serial_interface_dict_config(self, m_ispi5, m_subp):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {"console": True, "hardware": False}

        # Simulate is_pifive returning True to prevent enable_hw override
        with mock.patch.object(
            cloud.distro, "shutdown_command", return_value=["reboot"]
        ):
            cc_rpi.configure_serial_interface(cfg, {}, cloud)

        expected_calls = [
            mock.call(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    cc_rpi.RASPI_CONFIG_SERIAL_CONS_FN,
                    "0",
                ]
            ),
            mock.call(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    cc_rpi.RASPI_CONFIG_SERIAL_HW_FN,
                    "1",
                ]
            ),
            mock.call(["reboot"]),
        ]
        m_subp.assert_has_calls(expected_calls, any_order=False)

    @mock.patch("cloudinit.subp.subp")
    @mock.patch(M_PATH + "is_pifive", return_value=False)
    def test_configure_serial_interface_boolean_config_non_pi5(
        self, m_ispi5, m_subp
    ):
        cloud = get_cloud("raspberry_pi_os")

        with mock.patch.object(
            cloud.distro,
            "shutdown_command",
            return_value=["shutdown", "-r", "now"],
        ):
            cc_rpi.configure_serial_interface(True, {}, cloud)

        expected_calls = [
            mock.call(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    cc_rpi.RASPI_CONFIG_SERIAL_CONS_FN,
                    "0",
                ]
            ),
            mock.call(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    cc_rpi.RASPI_CONFIG_SERIAL_HW_FN,
                    "0",
                ]
            ),
            mock.call(["shutdown", "-r", "now"]),
        ]
        m_subp.assert_has_calls(expected_calls, any_order=False)


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
                f"{RPI_BASE_KEY}.{RPI_INTERFACES_KEY}.spi: 'true'"
                " is not of type 'boolean'",
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
                f"{RPI_BASE_KEY}.{RPI_INTERFACES_KEY}.serial.console: "
                "123 is not of type 'boolean'",
            ),
            ({RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: True}}, None),
            (
                {RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: "true"}},
                f"{RPI_BASE_KEY}.{ENABLE_RPI_CONNECT_KEY}: 'true'"
                " is not of type 'boolean'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
