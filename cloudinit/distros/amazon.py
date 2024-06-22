# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2014 Amazon.com, Inc. or its affiliates.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Andrew Jorgensen <ajorgens@amazon.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import rhel


class Distro(rhel.Distro):
    # Amazon Linux 2 stores dhclient leases at following location:
    # /var/lib/dhclient/dhclient--<iface_name>.leases
    # Perhaps there could be a UUID in between two "-" in the file name
    dhclient_lease_directory = "/var/lib/dhcp"
    dhclient_lease_file_regex = r"dhclient-[\w-]+\.lease"

    def update_package_sources(self, *, force=False):
        return None
