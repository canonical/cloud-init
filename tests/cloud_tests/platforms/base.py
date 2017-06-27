# This file is part of cloud-init. See LICENSE file for license information.

"""Base platform class."""


class Platform(object):
    """Base class for platforms."""

    platform_name = None

    def __init__(self, config):
        """Set up platform."""
        self.config = config

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        raise NotImplementedError

    def destroy(self):
        """Clean up platform data."""
        pass

# vi: ts=4 expandtab
