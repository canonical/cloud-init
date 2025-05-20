# Copyright (C) 2024-2025, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
from typing import Union

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)
RPI_BASE_KEY = "rpi"
RPI_INTERFACES_KEY = "interfaces"
ENABLE_RPI_CONNECT_KEY = "enable_rpi_connect"
SUPPORTED_INTERFACES = {
    "spi": "do_spi",
    "i2c": "do_i2c",
    "serial": "do_serial",
    "onewire": "do_onewire",
    "remote_gpio": "do_rgpio",
}
RASPI_CONFIG_SERIAL_CONS_FN = "do_serial_cons"
RASPI_CONFIG_SERIAL_HW_FN = "do_serial_hw"

meta: MetaSchema = {
    "id": "cc_raspberry_pi",
    "distros": ["raspberry-pi-os"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [RPI_BASE_KEY],
}


def configure_rpi_connect(enable: bool) -> None:
    LOG.debug("Configuring rpi-connect: %s", enable)

    num = 0 if enable else 1

    try:
        subp.subp(["/usr/bin/raspi-config", "do_rpi_connect", str(num)])
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure rpi-connect: %s", e)


def is_pifive() -> bool:
    try:
        subp.subp(["/usr/bin/raspi-config", "nonint", "is_pifive"])
        return True
    except subp.ProcessExecutionError:
        return False


def configure_serial_interface(
    cfg: Union[dict, bool], instCfg: Config, cloud: Cloud
) -> None:
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

        try:
            subp.subp(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    RASPI_CONFIG_SERIAL_HW_FN,
                    str(0 if enable_hw else 1),
                ]
            )
        except subp.ProcessExecutionError as e:
            LOG.error("Failed to configure serial hardware: %s", e)

        # Reboot to apply changes
        cmd = cloud.distro.shutdown_command(
            mode="reboot",
            delay="now",
            message="Rebooting to apply serial console changes",
        )
        subp.subp(cmd)
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure serial console: %s", e)


def configure_interface(iface: str, enable: bool) -> None:
    assert (
        iface in SUPPORTED_INTERFACES.keys() and iface != "serial"
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
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure %s: %s", iface, e)


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

    for key in cfg[RPI_BASE_KEY]:
        if key == ENABLE_RPI_CONNECT_KEY:
            enable = cfg[RPI_BASE_KEY][key]

            if isinstance(enable, bool):
                configure_rpi_connect(enable)
            else:
                LOG.warning(
                    "Invalid value for %s: %s", ENABLE_RPI_CONNECT_KEY, enable
                )
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
            # Move " serial" to the end if it exists
            if "serial" in subkeys:
                subkeys.append(subkeys.pop(subkeys.index("serial")))

            # check for supported ARM interfaces
            for subkey in subkeys:
                if subkey not in SUPPORTED_INTERFACES.keys():
                    LOG.warning(
                        "Invalid key for %s: %s", RPI_INTERFACES_KEY, subkey
                    )
                    continue

                enable = cfg[RPI_BASE_KEY][key][subkey]

                if subkey == "serial":
                    if not isinstance(enable, (dict, bool)):
                        LOG.warning(
                            "Invalid value for %s.%s: %s",
                            RPI_INTERFACES_KEY,
                            subkey,
                            enable,
                        )
                    else:
                        configure_serial_interface(enable, cfg, cloud)
                    continue

                if isinstance(enable, bool):
                    configure_interface(subkey, enable)
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
