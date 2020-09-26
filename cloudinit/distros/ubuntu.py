# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import debian
from cloudinit.distros import PREFERRED_NTP_CLIENTS
from cloudinit import util

import copy


class Distro(debian.Distro):

    def __init__(self, name, cfg, paths):
        super(Distro, self).__init__(name, cfg, paths)
        # Ubuntu specific network cfg locations
        self.network_conf_fn = {
            "eni": "/etc/network/interfaces.d/50-cloud-init.cfg",
            "netplan": "/etc/netplan/50-cloud-init.yaml"
        }
        self.renderer_configs = {
            "eni": {"eni_path": self.network_conf_fn["eni"],
                    "eni_header": debian.NETWORK_FILE_HEADER},
            "netplan": {"netplan_path": self.network_conf_fn["netplan"],
                        "netplan_header": debian.NETWORK_FILE_HEADER,
                        "postcmds": True}
        }

    @property
    def preferred_ntp_clients(self):
        """The preferred ntp client is dependent on the version."""
        if not self._preferred_ntp_clients:
            (_name, _version, codename) = util.system_info()['dist']
            # Xenial cloud-init only installed ntp, UbuntuCore has timesyncd.
            if codename == "xenial" and not util.system_is_snappy():
                self._preferred_ntp_clients = ['ntp']
            else:
                self._preferred_ntp_clients = (
                    copy.deepcopy(PREFERRED_NTP_CLIENTS))
        return self._preferred_ntp_clients


# vi: ts=4 expandtab
