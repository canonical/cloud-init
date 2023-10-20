# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import rhel


class Distro(rhel.Distro):
    def __init__(self, name, cfg, paths):
        super(Distro, self).__init__(name, cfg, paths)
        self.osfamily = "openeuler"
