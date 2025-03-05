"""Bootc: Switch to a different bootc image."""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_bootc",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["bootc"],
}

LOG = logging.getLogger(__name__)

def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    bootc = cfg.get('bootc')
    if not bootc:
        LOG.warning("No 'bootc' configuration found, skipping.")
        return

    image = util.get_cfg_option_str(bootc, "image")
    if not image:
        raise ValueError("No 'image' specified in the 'bootc' configuration.")

    # If Podman is not installed, install it
    if not os.path.exists("/usr/bin/podman"):
        install_podman(cloud, image)

    LOG.info(f"Switching to bootc image: {image}")

    try:
        pull_image(image)
        install_to_existing_root(image)
    except Exception as e:
        LOG.error(f"Failed to switch to bootc image: {e}")
        raise

    LOG.info("Successfully switched to bootc image")
    _fire_reboot()


def install_podman(cloud: Cloud, image: str) -> None:
    LOG.info(f"Installing Podman")

    try:
        cloud.distri.install_packages(["podman"])
    except Exception as e:
        LOG.error(f"Failed to install Podman: {e}")
        raise


def pull_image(image: str) -> None:
    LOG.info(f"Pulling bootc image: {image}")

    try:
        command = ["podman", "pull", "--tls-verify=false", image]
        subp.subp(command)
        LOG.info(f"Successfully executed: {' '.join(command)}")
    except Exception as e:
        LOG.error(f"Command failed with error: {e}")
        raise


def install_to_existing_root(image: str) -> None:
    LOG.info(f"Installing bootc to existing root")

    try:
        command = [
            "podman",
            "run",
            "--rm",
            "--privileged",
            "--volume", "/dev:/dev",
            "--volume", "/var/lib/containers:/var/lib/containers",
            "--volume", "/:/target",
            "--pid=host",
            "--tls-verify=false",
            "--security-opt", "label=type:unconfined_t",
            image,
            "bootc",
            "install",
            "to-existing-root",
        ]
        subp.subp(command)
        LOG.info(f"Successfully executed: {' '.join(command)}")
    except Exception as e:
        LOG.error(f"Command failed with error: {e}")
        raise


# Taken from cc_package_update_upgrade_install.py
def _fire_reboot(
    wait_attempts: int = 6, initial_sleep: int = 1, backoff: int = 2
):
    """Run a reboot command and panic if it doesn't happen fast enough."""
    subp.subp(REBOOT_CMD)
    start = time.monotonic()
    wait_time = initial_sleep
    for _i in range(wait_attempts):
        time.sleep(wait_time)
        wait_time *= backoff
        elapsed = time.monotonic() - start
        LOG.debug("Rebooted, but still running after %s seconds", int(elapsed))
    # If we got here, not good
    elapsed = time.monotonic() - start
    raise RuntimeError(
        "Reboot did not happen after %s seconds!" % (int(elapsed))
    )
