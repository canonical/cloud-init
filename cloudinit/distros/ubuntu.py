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
from cloudinit import log as logging
from cloudinit import util

import copy

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):

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

    pass


# vi: ts=4 expandtab
