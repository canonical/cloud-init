# This file is part of cloud-init. See LICENSE file for license information.

"""Base Azure Cloud snapshot."""

from ..snapshots import Snapshot

from tests.cloud_tests import LOG


class AzureCloudSnapshot(Snapshot):
    """Azure Cloud image copy backed snapshot."""

    platform_name = 'azurecloud'

    def __init__(self, platform, properties, config, features, image_id,
                 delete_on_destroy=True):
        """Set up snapshot.

        @param platform: platform object
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        super(AzureCloudSnapshot, self).__init__(
            platform, properties, config, features)

        self.image_id = image_id
        self.delete_on_destroy = delete_on_destroy

    def launch(self, user_data, meta_data=None, block=True, start=True,
               use_desc=None):
        """Launch instance.

        @param user_data: user-data for the instance
        @param meta_data: meta_data for the instance
        @param block: wait until instance is created
        @param start: start instance and wait until fully started
        @param use_desc: description of snapshot instance use
        @return_value: an Instance
        """
        if meta_data is not None:
            raise ValueError("metadata not supported on Azure Cloud tests")

        instance = self.platform.create_instance(
            self.properties, self.config, self.features,
            self.image_id, user_data)

        return instance

    def destroy(self):
        """Clean up snapshot data."""
        LOG.debug('destroying image %s', self.image_id)
        if self.delete_on_destroy:
            self.platform.compute_client.images.delete(
                self.platform.resource_group.name,
                self.image_id)

# vi: ts=4 expandtab
