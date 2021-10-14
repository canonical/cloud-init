# This file is part of cloud-init. See LICENSE file for license information.
"""
Install Hotplug
--------------
**Summary:** Install hotplug if supported and enabled

This module will install the udev rules to enable hotplug if supported by
the datasource and enabled in the userdata. The udev rules will be installed
as ``/etc/udev/rules.d/10-cloud-init-hook-hotplug.rules``.

**Internal name:** ``cc_install_hotplug``

**Module frequency:** always

**Supported distros:** all

**Config keys**::

    updates:
      network:
        when: ['hotplug']
"""
import os

from cloudinit import util
from cloudinit import subp
from cloudinit import stages
from cloudinit.event import EventType, EventScope
from cloudinit.settings import PER_ALWAYS


frequency = PER_ALWAYS
distros = ['all']


HOTPLUG_UDEV_PATH = "/etc/udev/rules.d/10-cloud-init-hook-hotplug.rules"
HOTPLUG_UDEV_RULES = """\
ACTION!="add|remove", GOTO="cloudinit_end"
LABEL="cloudinit_hook"
SUBSYSTEM=="net", RUN+="/usr/lib/cloud-init/hook-hotplug"
LABEL="cloudinit_end"
"""


def handle(_name, cfg, cloud, log, _args):
    if not stages.update_event_enabled(
        datasource=cloud.datasource,
        cfg=cfg,
        event_source_type=EventType.HOTPLUG,
        scope=EventScope.NETWORK,
    ):
        if os.path.exists(HOTPLUG_UDEV_PATH):
            log.debug("Uninstalling hotplug, not enabled")
            util.del_file(HOTPLUG_UDEV_PATH)
            subp.subp(['udevadm', 'control', '--reload-rules'])
        else:
            log.debug("Skipping hotplug install, not enabled")
        return
    if not subp.which('udevadm'):
        log.debug("Skipping hotplug install, udevadm not found")
        return

    util.write_file(
        filename=HOTPLUG_UDEV_PATH,
        content=HOTPLUG_UDEV_RULES,
    )
    subp.subp(['udevadm', 'control', '--reload-rules'])
