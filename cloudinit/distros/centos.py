# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros import DefaultCACertsAction, rhel


class Distro(rhel.Distro):
    ca_cert_remove_defaults_action = DefaultCACertsAction.NOOP
