# This file is part of cloud-init. See LICENSE file for license information.

"""EC2 Image Base Class."""

from ..images import Image
from .snapshot import EC2Snapshot
from tests.cloud_tests import LOG


class EC2Image(Image):
    """EC2 backed image."""

    platform_name = 'ec2'

    def __init__(self, platform, config, image_ami):
        """Set up image.

        @param platform: platform object
        @param config: image configuration
        @param image_ami: string of image ami ID
        """
        super(EC2Image, self).__init__(platform, config)
        self._img_instance = None
        self.image_ami = image_ami

    @property
    def _instance(self):
        """Internal use only, returns a running instance"""
        if not self._img_instance:
            self._img_instance = self.platform.create_instance(
                self.properties, self.config, self.features,
                self.image_ami, user_data=None)
            self._img_instance.start(wait=True, wait_for_cloud_init=True)
        return self._img_instance

    def destroy(self):
        """Delete the instance used to create a custom image."""
        if self._img_instance:
            LOG.debug('terminating backing instance %s',
                      self._img_instance.instance.instance_id)
            self._img_instance.instance.terminate()
            self._img_instance.instance.wait_until_terminated()

        super(EC2Image, self).destroy()

    def _execute(self, *args, **kwargs):
        """Execute command in image, modifying image."""
        self._instance.start(wait=True)
        return self._instance._execute(*args, **kwargs)

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'."""
        self._instance.start(wait=True)
        return self._instance.push_file(local_path, remote_path)

    def run_script(self, *args, **kwargs):
        """Run script in image, modifying image.

        @return_value: script output
        """
        self._instance.start(wait=True)
        return self._instance.run_script(*args, **kwargs)

    def snapshot(self):
        """Create snapshot of image, block until done.

        Will return base image_ami if no instance has been booted, otherwise
        will run the clean script, shutdown the instance, create a custom
        AMI, and use that AMI once available.
        """
        if not self._img_instance:
            return EC2Snapshot(self.platform, self.properties, self.config,
                               self.features, self.image_ami,
                               delete_on_destroy=False)

        if self.config.get('boot_clean_script'):
            self._img_instance.run_script(self.config.get('boot_clean_script'))

        self._img_instance.shutdown(wait=True)

        LOG.debug('creating custom ami from instance %s',
                  self._img_instance.instance.instance_id)
        response = self.platform.ec2_client.create_image(
            Name='%s-%s' % (self.platform.tag, self.image_ami),
            InstanceId=self._img_instance.instance.instance_id
        )
        image_ami_edited = response['ImageId']

        # Create image and wait until it is in the 'available' state
        image = self.platform.ec2_resource.Image(image_ami_edited)
        image.wait_until_exists()
        waiter = self.platform.ec2_client.get_waiter('image_available')
        waiter.wait(ImageIds=[image.id])
        image.reload()

        return EC2Snapshot(self.platform, self.properties, self.config,
                           self.features, image_ami_edited)

# vi: ts=4 expandtab
