# This file is part of cloud-init. See LICENSE file for license information.


def get_snapshot(image):
    """
    get snapshot from image
    """
    return image.snapshot()

# vi: ts=4 expandtab
