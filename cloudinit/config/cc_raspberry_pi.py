# Copyright (C) 2024-2025, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
from typing import Union

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)
RPI_BASE_KEY = "rpi"
RPI_INTERFACES_KEY = "interfaces"
ENABLE_USB_GADGET_KEY = "enable_usb_gadget"
SUPPORTED_INTERFACES = {
    "spi": "do_spi",
    "i2c": "do_i2c",
    "onewire": "do_onewire",
}
SERIAL_INTERFACE = "serial"
RASPI_CONFIG_SERIAL_CONS_FN = "do_serial_cons"
RASPI_CONFIG_SERIAL_HW_FN = "do_serial_hw"
RPI_USB_GADGET_SCRIPT = "/usr/bin/rpi-usb-gadget"
REBOOT_MSG = "Rebooting to apply config.txt changes..."

meta: MetaSchema = {
    "id": "cc_raspberry_pi",
    "distros": ["raspberry-pi-os"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [RPI_BASE_KEY],
}


def configure_usb_gadget(enable: bool) -> bool:
    """Enable / Disable Raspberry Pi USB gadget mode when
    the script is present.

    Returns True when a reboot is required.
    """
    LOG.debug("Enable rpi-usb-gadget mode: %s", enable)

    if not os.path.exists(RPI_USB_GADGET_SCRIPT):
        LOG.error("rpi-usb-gadget script not found: %s", RPI_USB_GADGET_SCRIPT)
        return False

    try:
        subp.subp(
            [
                RPI_USB_GADGET_SCRIPT,
                "on" if enable else "off",
                # Force even if the device isn't supported
                # to avoid timeout in action request
                # and to allow activation with microSD card
                # in a unsupported device because its maybe faster
                # and then the user might switch it to a
                # supported device later
                "-f",
            ],
            capture=False,
            timeout=15,
        )

        return True
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure rpi-usb-gadget: %s", e)
        return False


def is_pifive() -> bool:
    try:
        subp.subp(["/usr/bin/raspi-config", "nonint", "is_pifive"])
        return True
    except subp.ProcessExecutionError:
        return False


def configure_serial_interface(cfg: Union[dict, bool]) -> bool:
    """Configure the serial (UART) interface on Raspberry Pi.

    Depending on the configuration, this enables or disables
    the serial console and the hardware UART by invoking
    `raspi-config` non-interactively.

    Args:
        cfg: Either a boolean or a dictionary:
            - If a bool, enables or disables the serial
              console and hardware UART together.
            - If a dict, may contain the keys `console`
              and `hardware` with boolean values controlling
              each individually.

    Returns:
        True if the configuration was applied successfully,
        False otherwise.
    """

    def get_bool_field(cfg_dict: dict, name: str, default=False):
        val = cfg_dict.get(name, default)
        if not isinstance(val, bool):
            LOG.warning(
                "Invalid value for %s.serial.%s: %s",
                RPI_INTERFACES_KEY,
                name,
                val,
            )
            return default
        return val

    enable_console = False
    enable_hw = False

    if isinstance(cfg, dict):
        enable_console = get_bool_field(cfg, "console")
        enable_hw = get_bool_field(cfg, "hardware")

    elif isinstance(cfg, bool):
        # default to enabling console as if < pi5
        # this will also enable the hardware
        enable_console = cfg

    if not is_pifive() and enable_console:
        # only pi5 has 2 usable UARTs
        # on other models, enabling the console
        # will also block the other UART
        enable_hw = True

    try:
        subp.subp(
            [
                "/usr/bin/raspi-config",
                "nonint",
                RASPI_CONFIG_SERIAL_CONS_FN,
                str(0 if enable_console else 1),
            ]
        )
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure serial console: %s", e)
        return False

    try:
        subp.subp(
            [
                "/usr/bin/raspi-config",
                "nonint",
                RASPI_CONFIG_SERIAL_HW_FN,
                str(0 if enable_hw else 1),
            ]
        )
        return True
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure serial hardware: %s", e)
        return False


def configure_interface(iface: str, enable: bool) -> bool:
    """Enable or disable a supported hardware interface.

    Supported interfaces are defined in `SUPPORTED_INTERFACES` and
    currently include SPI, I2C, and 1-Wire. The function applies
    the change using `raspi-config` in non-interactive mode.

    Args:
        iface: The interface name (e.g. `"spi"` or `"i2c"`).
        enable: True to enable the interface, False to disable it.

    Returns:
        True if the interface configuration succeeded, False otherwise.
    """
    assert (
        iface in SUPPORTED_INTERFACES.keys()
    ), f"Unsupported interface: {iface}"

    try:
        subp.subp(
            [
                "/usr/bin/raspi-config",
                "nonint",
                SUPPORTED_INTERFACES[iface],
                str(0 if enable else 1),
            ]
        )

        return True
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure %s: %s", iface, e)
        return False


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if RPI_BASE_KEY not in cfg:
        return
    elif not isinstance(cfg[RPI_BASE_KEY], dict):
        LOG.warning(
            "Invalid value for %s: %s",
            RPI_BASE_KEY,
            cfg[RPI_BASE_KEY],
        )
        return
    elif not cfg[RPI_BASE_KEY]:
        LOG.debug("Empty value for %s. Skipping...", RPI_BASE_KEY)
        return

    want_reboot = False

    for key in cfg[RPI_BASE_KEY]:
        if key == ENABLE_USB_GADGET_KEY:
            enable = cfg[RPI_BASE_KEY][key]

            if isinstance(enable, bool):
                want_reboot |= configure_usb_gadget(enable)
            else:
                raise ValueError(f"Invalid value for {ENABLE_USB_GADGET_KEY}")
            continue
        elif key == RPI_INTERFACES_KEY:
            if not isinstance(cfg[RPI_BASE_KEY][key], dict):
                LOG.warning(
                    "Invalid value for %s: %s",
                    RPI_BASE_KEY,
                    cfg[RPI_BASE_KEY][key],
                )
                return
            elif not cfg[RPI_BASE_KEY][key]:
                LOG.debug("Empty value for %s. Skipping...", key)
                return

            subkeys = list(cfg[RPI_BASE_KEY][key].keys())

            # check for supported ARM interfaces
            for subkey in subkeys:
                if (
                    subkey not in SUPPORTED_INTERFACES.keys()
                    and subkey != SERIAL_INTERFACE
                ):
                    LOG.warning(
                        "Invalid key for %s: %s", RPI_INTERFACES_KEY, subkey
                    )
                    continue

                enable = cfg[RPI_BASE_KEY][key][subkey]

                if subkey == SERIAL_INTERFACE:
                    if not isinstance(enable, (dict, bool)):
                        LOG.warning(
                            "Invalid value for %s.%s: %s",
                            RPI_INTERFACES_KEY,
                            subkey,
                            enable,
                        )
                    else:
                        want_reboot |= configure_serial_interface(enable)
                    continue

                if isinstance(enable, bool):
                    want_reboot |= configure_interface(subkey, enable)
                else:
                    LOG.warning(
                        "Invalid value for %s.%s: %s",
                        RPI_INTERFACES_KEY,
                        subkey,
                        enable,
                    )
        else:
            LOG.warning("Unsupported key: %s", key)
            continue

    if want_reboot is True:
        # Reboot to apply changes to config.txt and modprobe
        cmd = cloud.distro.shutdown_command(
            mode="reboot",
            delay="now",
            message=REBOOT_MSG,
        )
        subp.subp(cmd)
