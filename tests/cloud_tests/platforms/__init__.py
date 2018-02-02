# This file is part of cloud-init. See LICENSE file for license information.

"""Main init."""

from .ec2 import platform as ec2
from .lxd import platform as lxd
from .nocloudkvm import platform as nocloudkvm

PLATFORMS = {
    'ec2': ec2.EC2Platform,
    'nocloud-kvm': nocloudkvm.NoCloudKVMPlatform,
    'lxd': lxd.LXDPlatform,
}


def get_image(platform, config):
    """Get image from platform object using os_name."""
    return platform.get_image(config)


def get_instance(snapshot, *args, **kwargs):
    """Get instance from snapshot."""
    return snapshot.launch(*args, **kwargs)


def get_platform(platform_name, config):
    """Get the platform object for 'platform_name' and init."""
    platform_cls = PLATFORMS.get(platform_name)
    if not platform_cls:
        raise ValueError('invalid platform name: {}'.format(platform_name))
    return platform_cls(config)


def get_snapshot(image):
    """Get snapshot from image."""
    return image.snapshot()


# vi: ts=4 expandtab
