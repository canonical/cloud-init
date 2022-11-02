#!/usr/bin/env python3
# vi: ts=4 expandtab
#
# Copyright (C) 2021 VMware Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit import log as logging
from cloudinit.distros import photon

LOG = logging.getLogger(__name__)

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource. Changes
# to it will not persist across an instance reboot. To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
"""


class Distro(photon.Distro):
    systemd_hostname_conf_fn = "/etc/hostname"
    network_conf_dir = "/etc/systemd/network/"
    systemd_locale_conf_fn = "/etc/locale.conf"
    resolve_conf_fn = "/etc/systemd/resolved.conf"

    network_conf_fn = {"netplan": "/etc/netplan/50-cloud-init.yaml"}
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

    # Should be fqdn if we can use it
    prefer_fqdn = True

    def __init__(self, name, cfg, paths):
        photon.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "mariner"
        self.init_cmd = ["systemctl"]

    def _get_localhost_ip(self):
        return "127.0.0.1"
