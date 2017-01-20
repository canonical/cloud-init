# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests.platforms import lxd

PLATFORMS = {
    'lxd': lxd.LXDPlatform,
}


def get_platform(platform_name, config):
    """
    Get the platform object for 'platform_name' and init
    """
    platform_cls = PLATFORMS.get(platform_name)
    if not platform_cls:
        raise ValueError('invalid platform name: {}'.format(platform_name))
    return platform_cls(config)

# vi: ts=4 expandtab
