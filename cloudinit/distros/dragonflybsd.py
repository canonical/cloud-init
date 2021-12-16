# Copyright (C) 2020-2021 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import cloudinit.distros.freebsd


class Distro(cloudinit.distros.freebsd.Distro):
    home_dir = "/home"


# vi: ts=4 expandtab
