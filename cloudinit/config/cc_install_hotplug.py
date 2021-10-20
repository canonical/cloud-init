# This file is part of cloud-init. See LICENSE file for license information.
"""Install hotplug udev rules if supported and enabled"""
import os
from textwrap import dedent

from cloudinit import util
from cloudinit import subp
from cloudinit import stages
from cloudinit.config.schema import get_schema_doc, validate_cloudconfig_schema
from cloudinit.distros import ALL_DISTROS
from cloudinit.event import EventType, EventScope
from cloudinit.settings import PER_ALWAYS


frequency = PER_ALWAYS
distros = [ALL_DISTROS]

schema = {
    "id": "cc_install_hotplug",
    "name": "Install Hotplug",
    "title": "Install hotplug if supported and enabled",
    "description": dedent("""\
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
    """),
    "distros": distros,
    "examples": [
        dedent("""\
            # Enable hotplug of network devices
            updates:
              network:
                when: ["hotplug"]
        """),
        dedent("""\
            # Enalble network hotplug alongside boot event
            updates:
              network:
                when: ["boot", "hotplug"]
        """),
    ],
    "frequency": frequency,
    "type": "object",
    "properties": {
        "updates": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "network": {
                    "type": "object",
                    "required": ["when"],
                    "additionalProperties": False,
                    "properties": {
                        "when": {
                            "type": "array",
                            "additionalProperties": False,
                            "items": {
                                "type": "string",
                                "additionalProperties": False,
                                "enum": [
                                    "boot-new-instance",
                                    "boot-legacy",
                                    "boot",
                                    "hotplug",
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
}

__doc__ == get_schema_doc(schema)


HOTPLUG_UDEV_PATH = "/etc/udev/rules.d/10-cloud-init-hook-hotplug.rules"
HOTPLUG_UDEV_RULES = """\
ACTION!="add|remove", GOTO="cloudinit_end"
LABEL="cloudinit_hook"
SUBSYSTEM=="net", RUN+="/usr/lib/cloud-init/hook-hotplug"
LABEL="cloudinit_end"
"""


def handle(_name, cfg, cloud, log, _args):
    validate_cloudconfig_schema(cfg, schema)
    network_hotplug_enabled = (
        'updates' in cfg and
        'network' in cfg['updates'] and
        'when' in cfg['updates']['network'] and
        'hotplug' in cfg['updates']['network']['when']
    )
    if not (
        EventType.HOTPLUG in cloud.datasource.get_supported_events(
            [EventType.HOTPLUG]
        ) and
        stages.update_event_enabled(
            datasource=cloud.datasource,
            cfg=cfg,
            event_source_type=EventType.HOTPLUG,
            scope=EventScope.NETWORK,
        )
    ):
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

    util.write_file(
        filename=HOTPLUG_UDEV_PATH,
        content=HOTPLUG_UDEV_RULES,
    )
    subp.subp(["udevadm", "control", "--reload-rules"])
