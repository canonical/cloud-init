# This file is part of cloud-init. See LICENSE file for license information.

"""Base class for images."""


class Image(object):
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
        raise NotImplementedError

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

    def execute(self, *args, **kwargs):
        """Execute command in image, modifying image."""
        raise NotImplementedError

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'."""
        raise NotImplementedError

    def run_script(self, *args, **kwargs):
        """Run script in image, modifying image.

        @return_value: script output
        """
        raise NotImplementedError

    def snapshot(self):
        """Create snapshot of image, block until done."""
        raise NotImplementedError

    def destroy(self):
        """Clean up data associated with image."""
        pass

# vi: ts=4 expandtab
