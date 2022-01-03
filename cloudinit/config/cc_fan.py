# Copyright (C) 2015 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Fan
---
**Summary:** configure ubuntu fan networking

This module installs, configures and starts the ubuntu fan network system. For
more information about Ubuntu Fan, see:
``https://wiki.ubuntu.com/FanNetworking``.

If cloud-init sees a ``fan`` entry in cloud-config it will:

    - write ``config_path`` with the contents of the ``config`` key
    - install the package ``ubuntu-fan`` if it is not installed
    - ensure the service is started (or restarted if was previously running)

**Internal name:** ``cc_fan``

**Module frequency:** per instance

**Supported distros:** ubuntu

**Config keys**::

    fan:
        config: |
            # fan 240
            10.0.0.0/8 eth0/16 dhcp
            10.0.0.0/8 eth1/16 dhcp off
            # fan 241
            241.0.0.0/8 eth0/16 dhcp
        config_path: /etc/network/fan
"""

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE

BUILTIN_CFG = {
    "config": None,
    "config_path": "/etc/network/fan",
}


def stop_update_start(distro, service, config_file, content):
    try:
        distro.manage_service("stop", service)
        stop_failed = False
    except subp.ProcessExecutionError as e:
        stop_failed = True
        LOG.warning("failed to stop %s: %s", service, e)

    if not content.endswith("\n"):
        content += "\n"
    util.write_file(config_file, content, omode="w")

    try:
        distro.manage_service("start", service)
        if stop_failed:
            LOG.warning("success: %s started", service)
    except subp.ProcessExecutionError as e:
        LOG.warning("failed to start %s: %s", service, e)

    distro.manage_service("enable", service)


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get("fan")
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    if not mycfg.get("config"):
        LOG.debug("%s: no 'fan' config entry. disabling", name)
        return

    util.write_file(mycfg.get("config_path"), mycfg.get("config"), omode="w")
    distro = cloud.distro
    if not subp.which("fanctl"):
        distro.install_packages(["ubuntu-fan"])

    stop_update_start(
        distro,
        service="ubuntu-fan",
        config_file=mycfg.get("config_path"),
        content=mycfg.get("config"),
    )


# vi: ts=4 expandtab
