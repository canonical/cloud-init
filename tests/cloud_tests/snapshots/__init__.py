# This file is part of cloud-init. See LICENSE file for license information.

"""Main init."""


def get_snapshot(image):
    """Get snapshot from image."""
    return image.snapshot()

# vi: ts=4 expandtab
