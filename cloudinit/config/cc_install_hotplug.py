# This file is part of cloud-init. See LICENSE file for license information.
"""Install hotplug udev rules if supported and enabled"""
import logging
import os

from cloudinit import stages, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.event import EventScope, EventType
from cloudinit.settings import PER_INSTANCE
from cloudinit.sources import DataSource

meta: MetaSchema = {
    "id": "cc_install_hotplug",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


# 90 to be sorted after 80-net-setup-link.rules which sets ID_NET_DRIVER and
# some datasources match on drivers
HOTPLUG_UDEV_PATH = "/etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
HOTPLUG_UDEV_RULES_TEMPLATE = """\
# Installed by cloud-init due to network hotplug userdata
ACTION!="add|remove", GOTO="cloudinit_end"{extra_rules}
LABEL="cloudinit_hook"
SUBSYSTEM=="net", RUN+="{libexecdir}/hook-hotplug"
LABEL="cloudinit_end"
"""


def install_hotplug(
    datasource: DataSource,
    cfg: Config,
    network_hotplug_enabled: bool,
):
    hotplug_supported = EventType.HOTPLUG in (
        datasource.get_supported_events([EventType.HOTPLUG]).get(
            EventScope.NETWORK, set()
        )
    )
    hotplug_enabled = stages.update_event_enabled(
        datasource=datasource,
        cfg=cfg,
        event_source_type=EventType.HOTPLUG,
        scope=EventScope.NETWORK,
    )
    if not (hotplug_supported and hotplug_enabled):
        if os.path.exists(HOTPLUG_UDEV_PATH):
            LOG.debug("Uninstalling hotplug, not enabled")
            util.del_file(HOTPLUG_UDEV_PATH)
            subp.subp(["udevadm", "control", "--reload-rules"])
        elif network_hotplug_enabled:
            LOG.warning(
                "Hotplug is unsupported by current datasource. "
                "Udev rules will NOT be installed."
            )
        else:
            LOG.debug("Skipping hotplug install, not enabled")
        return
    if not subp.which("udevadm"):
        LOG.debug("Skipping hotplug install, udevadm not found")
        return

    extra_rules = (
        datasource.extra_hotplug_udev_rules
        if datasource.extra_hotplug_udev_rules is not None
        else ""
    )
    if extra_rules:
        extra_rules = "\n" + extra_rules
    # This may need to turn into a distro property at some point
    libexecdir = "/usr/libexec/cloud-init"
    if not os.path.exists(libexecdir):
        libexecdir = "/usr/lib/cloud-init"
    LOG.info("Installing hotplug.")
    util.write_file(
        filename=HOTPLUG_UDEV_PATH,
        content=HOTPLUG_UDEV_RULES_TEMPLATE.format(
            extra_rules=extra_rules, libexecdir=libexecdir
        ),
    )
    subp.subp(["udevadm", "control", "--reload-rules"])


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    network_hotplug_enabled = (
        "updates" in cfg
        and "network" in cfg["updates"]
        and "when" in cfg["updates"]["network"]
        and "hotplug" in cfg["updates"]["network"]["when"]
    )
    install_hotplug(cloud.datasource, cfg, network_hotplug_enabled)
