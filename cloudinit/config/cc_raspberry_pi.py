# Copyright (C) 2024-2025, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

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


# TODO: test
def require_reboot(cfg: Config) -> None:
    cfg["power_state"] = cfg.get("power_state", {})
    cfg["power_state"]["mode"] = cfg["power_state"].get("mode", "reboot")
    cfg["power_state"]["condition"] = True


def is_pifive() -> bool:
    try:
        subp.subp(["/usr/bin/raspi-config", "nonint", "is_pifive"])
        return True
    except subp.ProcessExecutionError:
        return False


def configure_serial_interface(cfg: dict | bool, instCfg: Config) -> None:
    enable_console = False
    enable_hw = False

    if isinstance(cfg, dict):
        enable_console = cfg.get("console", False)
        enable_hw = cfg.get("hardware", False)
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

        require_reboot(instCfg)
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
            # expect it to be a dictionary
            enable = cfg[ENABLE_RPI_CONNECT_KEY]

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

            # check for supported ARM interfaces
            for subkey in cfg[RPI_BASE_KEY][key]:
                if subkey not in SUPPORTED_INTERFACES.keys():
                    LOG.warning(
                        "Invalid key for %s: %s", RPI_INTERFACES_KEY, subkey
                    )
                    continue

                enable = cfg[RPI_INTERFACES_KEY][subkey]

                if subkey == "serial":
                    if not isinstance(enable, dict) and not isinstance(
                        enable, bool
                    ):
                        LOG.warning(
                            "Invalid value for %s.%s: %s",
                            RPI_INTERFACES_KEY,
                            subkey,
                            enable,
                        )
                    else:
                        configure_serial_interface(enable, cfg)
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
