# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import gentoo


# Support for Container-Optimized OS
# https://cloud.google.com/container-optimized-os/docs
class Distro(gentoo.Distro):
    pass


# vi: ts=4 expandtab
