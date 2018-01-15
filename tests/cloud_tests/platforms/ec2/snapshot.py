# This file is part of cloud-init. See LICENSE file for license information.

"""Base EC2 snapshot."""

from ..snapshots import Snapshot
from tests.cloud_tests import LOG


class EC2Snapshot(Snapshot):
    """EC2 image copy backed snapshot."""

    platform_name = 'ec2'

    def __init__(self, platform, properties, config, features, image_ami,
                 delete_on_destroy=True):
        """Set up snapshot.

        @param platform: platform object
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        @param image_ami: string of image ami ID
        @param delete_on_destroy: boolean to delete on destroy
        """
        super(EC2Snapshot, self).__init__(
            platform, properties, config, features)

        self.image_ami = image_ami
        self.delete_on_destroy = delete_on_destroy

    def destroy(self):
        """Deregister the backing AMI."""
        if self.delete_on_destroy:
            image = self.platform.ec2_resource.Image(self.image_ami)
            snapshot_id = image.block_device_mappings[0]['Ebs']['SnapshotId']

            LOG.debug('removing custom ami %s', self.image_ami)
            self.platform.ec2_client.deregister_image(ImageId=self.image_ami)

            LOG.debug('removing custom snapshot %s', snapshot_id)
            self.platform.ec2_client.delete_snapshot(SnapshotId=snapshot_id)

    def launch(self, user_data, meta_data=None, block=True, start=True,
               use_desc=None):
        """Launch instance.

        @param user_data: user-data for the instance
        @param meta_data: meta_data for the instance
        @param block: wait until instance is created
        @param start: start instance and wait until fully started
        @param use_desc: string of test name
        @return_value: an Instance
        """
        if meta_data is not None:
            raise ValueError("metadata not supported on Ec2")

        instance = self.platform.create_instance(
            self.properties, self.config, self.features,
            self.image_ami, user_data)

        if start:
            instance.start()

        return instance

# vi: ts=4 expandtab
