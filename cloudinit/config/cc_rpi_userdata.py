# Copyright (C) 2024, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_ALWAYS
import logging
import os
import subprocess
import time

LOG = logging.getLogger(__name__)
DISABLE_PIWIZ_KEY = "disable_piwiz"
RPI_USERCONF_KEY = "rpi_userconf"
USERCONF_SERVICE_TTY = "/dev/tty8"
MODULE_DEACTIVATION_FILE = "/var/lib/userconf-pi/deactivate"

meta: MetaSchema = {
    "id": "cc_rpi_userdata",
    "distros": ["raspberry-pi-os"],
    # Run every boot to trigger setup wizard even when no settings
    "frequency": PER_ALWAYS,
    # "activate_by_schema_keys": [DISABLE_PIWIZ_KEY, RPI_USERCONF_KEY],
    # When provided it would only start the module
    # when the keys are present in the configuration
    "activate_by_schema_keys": [],
}


def bool_to_str(value: bool | None) -> str:
    return "Yes" if value else "No"


def get_fwloc_or_default() -> str:
    fwloc = None
    try:
        # Run the command and capture the output
        fwloc = subp.subp(
            ["/usr/lib/raspberrypi-sys-mods/get_fw_loc"], decode="strict"
        ).stdout.strip()

        # If the output is empty, set the default value
        if not fwloc:
            fwloc = "/boot"
    except subp.ProcessExecutionError:
        # If the command fails, set the default value
        fwloc = "/boot"
    return fwloc


def run_userconf_service(
    base: str | None, passwd_override: str | None = None
) -> bool:
    try:
        # reset the TTY device
        os.system(f"echo 'reset\\r\\n' > {USERCONF_SERVICE_TTY}")

        time.sleep(1)
        # Execute the command on different tty
        result = subp.subp(
            [
                "openvt",
                "-s",
                "-f",
                "-w",
                "-c",
                USERCONF_SERVICE_TTY[-1],
                "--",
                "/usr/lib/userconf-pi/userconf-service",
            ],
            timeout=(None if not passwd_override else 10),
            decode="strict",
        )

        if base:
            try:
                os.remove(f"{base}/userconf.txt")
            except FileNotFoundError:
                pass

        if result.stderr:
            # Handle failure and restart if needed (Restart=on-failure logic)
            LOG.debug(f"Userconf stderr service output: {result.stderr}")
            return False
        else:
            lib_dir = os.path.dirname(MODULE_DEACTIVATION_FILE)
            # create deactivation file
            os.system(
                f"mkdir -p {lib_dir} " "&& touch {MODULE_DEACTIVATION_FILE}"
            )
            LOG.debug("Userconf service completed successfully.")
            return True
    except subprocess.TimeoutExpired:
        if base and os.path.exists(f"{base}/failed_userconf.txt"):
            LOG.error("Invalid credentials provided for userconf-pi.")
            os.remove(f"{base}/failed_userconf.txt")
        else:
            LOG.error("Userconf service timed out.")
        return False
    except Exception as e:
        LOG.warning("Error running service: %s", e)
        if base:
            try:
                os.remove(f"{base}/userconf.txt")
            except FileNotFoundError:
                pass
        return False


def run_service(
    passwd_override: str | None = None, user_override: str | None = None
) -> bool:
    # Ensure the TTY exists before trying to open it
    if not os.path.exists(USERCONF_SERVICE_TTY):
        if not passwd_override:
            LOG.error("TTY device %s does not exist.", USERCONF_SERVICE_TTY)
            return False
        else:
            LOG.debug("TTY device %s does not exist.", USERCONF_SERVICE_TTY)

    # should never happen and not solvable by the user
    assert (passwd_override is None and user_override is None) or (
        passwd_override is not None and user_override is not None
    ), (
        "Internal error: User override is required when password "
        "override is provided."
    )

    base: str | None = None
    if passwd_override:
        # write /boot/firmware/userconf.txt
        # this will make userconf-service
        # run silently with the provided credentials
        base = get_fwloc_or_default()
        assert base, "Internal error: Failed to get firmware location."
        with open(f"{base}/userconf.txt", "w") as f:
            f.write(f"{user_override}:{passwd_override}")
        LOG.debug("Userconf override file written to %s/userconf.txt", base)

    LOG.debug("Start running userconf-pi service loop...")
    while True:
        if run_userconf_service(base, passwd_override):
            break
        # Wait for a moment before retrying
        time.sleep(1)
        LOG.debug("Userconf-pi service loop: retrying")
    LOG.debug("Userconf-pi service loop finished.")
    return True


def configure_pizwiz(
    cfg: Config,
    disable: bool,
    passwd_override: str | None,
    user_override: str | None = None,
) -> None:
    LOG.debug(
        "Configuring piwiz with disable_piwiz=%s, passwd_override=%s, "
        "user_override=%s",
        bool_to_str(disable),
        bool_to_str(passwd_override is not None),
        bool_to_str(user_override is not None),
    )

    if disable:
        # execute cancel rename script to ensure
        # piwiz isn't started (on desktop)
        os.system("/usr/bin/cancel-rename pi")
    else:
        # execute userconf-pi service
        # on desktop this doesn't have any effect
        # as piwiz is started by the desktop environment
        run_service(passwd_override, user_override)

        # populate users for other cloud-init modules to use
        cfg["users"] = cfg.get("users", [])
        if user_override and user_override not in cfg["users"]:
            cfg["users"].append(user_override)
        elif "pi" not in cfg["users"]:
            cfg["users"].append("pi")


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    disable_piwiz: bool = False
    password_override: str | None = None
    user_override: str | None = None

    if os.path.exists(MODULE_DEACTIVATION_FILE) or not os.path.exists(
        "/usr/lib/userconf-pi"
    ):
        LOG.debug(
            "Userconf-Pi: deactivation file detected or userconf-pi "
            "not installed. Skipping..."
        )
        return

    if RPI_USERCONF_KEY in cfg:
        # expect it to be a dictionary
        userconf = cfg[RPI_USERCONF_KEY]

        # look over miss configuration to
        if isinstance(userconf, dict) and "password" in userconf:
            password_override = userconf["password"]
            # user key is optional with default to pi
            user_override = userconf.get("user", "pi")
            LOG.debug(
                "Userconf override: user=%s, password=<REDACTED>",
                user_override,
            )
        else:
            LOG.error("Invalid userconf-pi configuration: %s", userconf)

    if not password_override and DISABLE_PIWIZ_KEY in cfg:
        if isinstance(cfg[DISABLE_PIWIZ_KEY], bool):
            disable_piwiz = cfg[DISABLE_PIWIZ_KEY]
        else:
            LOG.error(
                "Invalid %s configuration: %s",
                str(cfg[DISABLE_PIWIZ_KEY]),
                DISABLE_PIWIZ_KEY,
            )

    configure_pizwiz(cfg, disable_piwiz, password_override, user_override)
