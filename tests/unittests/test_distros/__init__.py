# This file is part of cloud-init. See LICENSE file for license information.
import copy

from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings


def _get_distro(dtype, system_info=None):
    """Return a Distro class of distro 'dtype'.

    cfg is format of CFG_BUILTIN['system_info'].

    example: _get_distro("debian")
    """
    if system_info is None:
        system_info = copy.deepcopy(settings.CFG_BUILTIN['system_info'])
    system_info['distro'] = dtype
    paths = helpers.Paths(system_info['paths'])
    distro_cls = distros.fetch(dtype)
    return distro_cls(dtype, system_info, paths)
