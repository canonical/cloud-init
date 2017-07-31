# This file is part of cloud-init. See LICENSE file for license information.

"""Main init."""


def get_image(platform, config):
    """Get image from platform object using os_name."""
    return platform.get_image(config)

# vi: ts=4 expandtab
