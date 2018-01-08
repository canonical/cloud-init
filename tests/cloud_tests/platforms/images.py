# This file is part of cloud-init. See LICENSE file for license information.

"""Base class for images."""

from ..util import TargetBase


class Image(TargetBase):
    """Base class for images."""

    platform_name = None

    def __init__(self, platform, config):
        """Set up image.

        @param platform: platform object
        @param config: image configuration
        """
        self.platform = platform
        self.config = config

    def __str__(self):
        """A brief description of the image."""
        return '-'.join((self.properties['os'], self.properties['release']))

    @property
    def properties(self):
        """{} containing: 'arch', 'os', 'version', 'release'."""
        return {k: self.config[k]
                for k in ('arch', 'os', 'release', 'version')}

    @property
    def features(self):
        """Feature flags supported by this image.

        @return_value: list of feature names
        """
        return [k for k, v in self.config.get('features', {}).items() if v]

    @property
    def setup_overrides(self):
        """Setup options that need to be overridden for the image.

        @return_value: dictionary to update args with
        """
        # NOTE: more sophisticated options may be requied at some point
        return self.config.get('setup_overrides', {})

    def snapshot(self):
        """Create snapshot of image, block until done."""
        raise NotImplementedError

    def destroy(self):
        """Clean up data associated with image."""
        pass

# vi: ts=4 expandtab
