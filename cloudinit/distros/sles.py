#    Copyright (C) 2017 SUSE LLC
#
#    Author: Robert Schweikert <rjschwei@suse.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import opensuse

from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class Distro(opensuse.Distro):
    pass

# vi: ts=4 expandtab
