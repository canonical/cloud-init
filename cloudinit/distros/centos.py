# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import rhel
from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class Distro(rhel.Distro):
    pass

# vi: ts=4 expandtab
