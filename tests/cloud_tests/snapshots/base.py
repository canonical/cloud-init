# This file is part of cloud-init. See LICENSE file for license information.

"""Base snapshot."""


class Snapshot(object):
    """Base class for snapshots."""

    platform_name = None

    def __init__(self, platform, properties, config, features):
        """Set up snapshot.

        @param platform: platform object
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        self.platform = platform
        self.properties = properties
        self.config = config
        self.features = features

    def __str__(self):
        """A brief description of the snapshot."""
        return '-'.join((self.properties['os'], self.properties['release']))

    def launch(self, user_data, meta_data=None, block=True, start=True,
               use_desc=None):
        """Launch instance.

        @param user_data: user-data for the instance
        @param instance_id: instance-id for the instance
        @param block: wait until instance is created
        @param start: start instance and wait until fully started
        @param use_desc: description of snapshot instance use
        @return_value: an Instance
        """
        raise NotImplementedError

    def destroy(self):
        """Clean up snapshot data."""
        pass

# vi: ts=4 expandtab
