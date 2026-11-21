# Copyright (C) 2024 Microsoft Corporation
#
# Author: Dan Streetman <ddstreet@microsoft.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit.distros import rhel
from cloudinit.net.netplan import CLOUDINIT_NETPLAN_FILE

LOG = logging.getLogger(__name__)

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot. To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
"""


class Distro(rhel.Distro):
    network_conf_dir = "/etc/systemd/network/"
    systemd_locale_conf_fn = "/etc/locale.conf"
    resolve_conf_fn = "/etc/systemd/resolved.conf"

    network_conf_fn = {"netplan": CLOUDINIT_NETPLAN_FILE}  # type: ignore[assignment]
    renderer_configs = {
        "networkd": {
            "resolv_conf_fn": resolve_conf_fn,
            "network_conf_dir": network_conf_dir,
        },
        "netplan": {
            "netplan_path": network_conf_fn["netplan"],
            "netplan_header": NETWORK_FILE_HEADER,
            "postcmds": "True",
        },
    }

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        self.osfamily = "azurelinux"
        self.init_cmd = ["systemctl"]
