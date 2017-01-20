# This file is part of cloud-init. See LICENSE file for license information.


def get_image(platform, config):
    """
    get image from platform object using os_name, looking up img_conf in main
    config file
    """
    return platform.get_image(config)

# vi: ts=4 expandtab
