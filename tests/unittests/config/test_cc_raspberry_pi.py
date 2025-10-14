# This file is part of cloud-init. See LICENSE file for license information.

import pytest

import cloudinit.config.cc_raspberry_pi as cc_rpi
from cloudinit.config.cc_raspberry_pi import (
    ENABLE_USB_GADGET_KEY,
    RPI_BASE_KEY,
    RPI_INTERFACES_KEY,
    RPI_USB_GADGET_SCRIPT,
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
    @mock.patch(M_PATH + "configure_usb_gadget")
    def test_handle_usb_gadget_enabled(self, m_usb_gadget):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {RPI_BASE_KEY: {ENABLE_USB_GADGET_KEY: True}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_usb_gadget.assert_called_once_with(True)

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
        m_serial.assert_called_once_with(serial_value)

    @mock.patch(M_PATH + "configure_serial_interface")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_handle_configure_serial_interface_bool(self, m_ispi5, m_serial):
        cloud = get_cloud("raspberry_pi_os")
        cfg = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"serial": True}}}
        cc_rpi.handle("cc_raspberry_pi", cfg, cloud, [])
        m_serial.assert_called_once_with(True)

    @mock.patch(
        "cloudinit.distros.raspberry_pi_os.Distro.shutdown_command",
        return_value=["shutdown", "-r", "now", cc_rpi.REBOOT_MSG],
    )
    @mock.patch("cloudinit.subp.subp")
    @mock.patch(M_PATH + "is_pifive", return_value=True)
    def test_trigger_reboot(self, is_pi5, m_subp, m_shutdown):
        keys = list(cc_rpi.SUPPORTED_INTERFACES.keys()) + [
            cc_rpi.SERIAL_INTERFACE
        ]
        cloud = get_cloud("raspberry_pi_os")

        for key in keys:
            cfg1 = {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {key: True}}}

            m_subp.reset_mock()
            m_shutdown.reset_mock()

            cc_rpi.handle("cc_raspberry_pi", cfg1, cloud, [])

            # Reboot requested via shutdown command
            m_shutdown.assert_called_once()

            # subp calls: raspi-config(s) + shutdown
            expected_calls = 3 if key == cc_rpi.SERIAL_INTERFACE else 2
            assert m_subp.call_count == expected_calls

            # Last call is the shutdown
            assert m_subp.call_args == mock.call(
                ["shutdown", "-r", "now", cc_rpi.REBOOT_MSG]
            )

        # enable_usb_gadget path: ensure script exists so the code runs
        with mock.patch(M_PATH + "os.path.exists", return_value=True):
            cfg2 = {RPI_BASE_KEY: {ENABLE_USB_GADGET_KEY: True}}

            m_subp.reset_mock()
            m_shutdown.reset_mock()

            cc_rpi.handle("cc_raspberry_pi", cfg2, cloud, [])

            m_shutdown.assert_called_once()
            # gadget script + shutdown
            assert m_subp.call_count == 2
            assert m_subp.call_args == mock.call(
                ["shutdown", "-r", "now", cc_rpi.REBOOT_MSG]
            )


class TestRaspberryPiMethods:
    @mock.patch("cloudinit.subp.subp")
    def test_configure_usb_gadget_enable(self, m_subp):
        with mock.patch("os.path.exists", return_value=True):
            cc_rpi.configure_usb_gadget(True)
        m_subp.assert_called_once_with(
            [RPI_USB_GADGET_SCRIPT, "on", "-f"], capture=False, timeout=15
        )

    @mock.patch("cloudinit.subp.subp")
    def test_configure_usb_gadget_missing_script(self, m_subp, caplog):
        """If the rpi-usb-gadget script is missing, log an error
        and return False."""
        # Simulate missing rpi-usb-gadget script
        with mock.patch("os.path.exists", return_value=False):
            with caplog.at_level("ERROR"):
                # Should not raise
                result = cc_rpi.configure_usb_gadget(True)

        # No subprocess call should be made
        m_subp.assert_not_called()

        # Verify an error was logged
        assert "rpi-usb-gadget script not found" in caplog.text

        # Reboot should not be requested
        assert result is False

    @mock.patch("cloudinit.subp.subp")
    def test_configure_usb_gadget_script_failure(self, m_subp, caplog):
        """If the rpi-usb-gadget script fails, log an error
        and return False."""
        m_subp.side_effect = cc_rpi.subp.ProcessExecutionError(
            cmd=[RPI_USB_GADGET_SCRIPT, "on", "-f"],
            exit_code=1,
            stdout="",
            stderr="fail",
        )

        with mock.patch("os.path.exists", return_value=True):
            with caplog.at_level("ERROR"):
                result = cc_rpi.configure_usb_gadget(True)

        # Subprocess should have been invoked once
        m_subp.assert_called_once_with(
            [RPI_USB_GADGET_SCRIPT, "on", "-f"], capture=False, timeout=15
        )

        # Error log should contain failure message
        assert "Failed to configure rpi-usb-gadget" in caplog.text

        # Function should return False (no reboot triggered)
        assert result is False

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
        cfg = {"console": True, "hardware": False}

        # Simulate is_pifive returning True to prevent enable_hw override
        cc_rpi.configure_serial_interface(cfg)

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
        ]
        m_subp.assert_has_calls(expected_calls, any_order=False)

    @mock.patch("cloudinit.subp.subp")
    @mock.patch(M_PATH + "is_pifive", return_value=False)
    def test_configure_serial_interface_boolean_config_non_pi5(
        self, m_ispi5, m_subp
    ):
        cc_rpi.configure_serial_interface(True)

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
            ({RPI_BASE_KEY: {ENABLE_USB_GADGET_KEY: True}}, None),
            (
                {RPI_BASE_KEY: {ENABLE_USB_GADGET_KEY: "true"}},
                f"{RPI_BASE_KEY}.{ENABLE_USB_GADGET_KEY}: 'true'"
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
