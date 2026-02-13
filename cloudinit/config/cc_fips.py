# This file is part of cloud-init. See LICENSE file for license information.
"""FIPS: Enable FIPS mode at first boot.

This module configures the system to boot with kernel FIPS mode enabled
(fips=1). Only Fedora, CentOS and RHEL are supported; other distros are
skipped. Configuration is applied to the bootloader; a reboot is required
for FIPS mode to take effect. Use the ``power_state`` module to schedule
a reboot after cloud-init completes.
"""

import logging

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import ProcessExecutionError

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_fips",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["fips"],
}


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if not cfg.get("fips", False):
        LOG.debug("FIPS not enabled in config, skipping")
        return
    if util.fips_enabled():
        LOG.debug("FIPS already enabled, skipping")
        return

    distro = cloud.distro
    # UKI path: FIPS is enabled via addon copied to loader/addons.
    if util.is_uki_system():
        distro.append_kernel_cmdline("fips=1")
        return

    # fips-mode-setup path
    # Can not rely on this path for UKI systems
    try:
        distro.install_packages(["crypto-policies-scripts"])
        subp.subp(["fips-mode-setup", "--enable"], capture=True)
        return
    except (ProcessExecutionError, FileNotFoundError):
        LOG.debug("fips-mode-setup not available, continuing")

    # GRUB path
    distro.append_kernel_cmdline("fips=1")
    try:
        distro.install_packages(["dracut-fips"])
        subp.subp(["dracut", "-f"], capture=True)
    except Exception as e:
        LOG.warning("dracut-fips setup failed: %s", e)
    return
