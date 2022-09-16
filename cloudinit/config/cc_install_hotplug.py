# This file is part of cloud-init. See LICENSE file for license information.
"""Install hotplug udev rules if supported and enabled"""
import os
from logging import Logger
from textwrap import dedent

from cloudinit import stages, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.event import EventScope, EventType
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_install_hotplug",
    "name": "Install Hotplug",
    "title": "Install hotplug udev rules if supported and enabled",
    "description": dedent(
        """\
        This module will install the udev rules to enable hotplug if
        supported by the datasource and enabled in the userdata. The udev
        rules will be installed as
        ``/etc/udev/rules.d/10-cloud-init-hook-hotplug.rules``.

        When hotplug is enabled, newly added network devices will be added
        to the system by cloud-init. After udev detects the event,
        cloud-init will referesh the instance metadata from the datasource,
        detect the device in the updated metadata, then apply the updated
        network configuration.

        Currently supported datasources: Openstack, EC2
    """
    ),
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            # Enable hotplug of network devices
            updates:
              network:
                when: ["hotplug"]
        """
        ),
        dedent(
            """\
            # Enable network hotplug alongside boot event
            updates:
              network:
                when: ["boot", "hotplug"]
        """
        ),
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


HOTPLUG_UDEV_PATH = "/etc/udev/rules.d/10-cloud-init-hook-hotplug.rules"
HOTPLUG_UDEV_RULES_TEMPLATE = """\
# Installed by cloud-init due to network hotplug userdata
ACTION!="add|remove", GOTO="cloudinit_end"
LABEL="cloudinit_hook"
SUBSYSTEM=="net", RUN+="{libexecdir}/hook-hotplug"
LABEL="cloudinit_end"
"""


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    network_hotplug_enabled = (
        "updates" in cfg
        and "network" in cfg["updates"]
        and "when" in cfg["updates"]["network"]
        and "hotplug" in cfg["updates"]["network"]["when"]
    )
    hotplug_supported = EventType.HOTPLUG in (
        cloud.datasource.get_supported_events([EventType.HOTPLUG]).get(
            EventScope.NETWORK, set()
        )
    )
    hotplug_enabled = stages.update_event_enabled(
        datasource=cloud.datasource,
        cfg=cfg,
        event_source_type=EventType.HOTPLUG,
        scope=EventScope.NETWORK,
    )
    if not (hotplug_supported and hotplug_enabled):
        if os.path.exists(HOTPLUG_UDEV_PATH):
            log.debug("Uninstalling hotplug, not enabled")
            util.del_file(HOTPLUG_UDEV_PATH)
            subp.subp(["udevadm", "control", "--reload-rules"])
        elif network_hotplug_enabled:
            log.warning(
                "Hotplug is unsupported by current datasource. "
                "Udev rules will NOT be installed."
            )
        else:
            log.debug("Skipping hotplug install, not enabled")
        return
    if not subp.which("udevadm"):
        log.debug("Skipping hotplug install, udevadm not found")
        return

    # This may need to turn into a distro property at some point
    libexecdir = "/usr/libexec/cloud-init"
    if not os.path.exists(libexecdir):
        libexecdir = "/usr/lib/cloud-init"
    util.write_file(
        filename=HOTPLUG_UDEV_PATH,
        content=HOTPLUG_UDEV_RULES_TEMPLATE.format(libexecdir=libexecdir),
    )
    subp.subp(["udevadm", "control", "--reload-rules"])
