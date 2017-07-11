# This file is part of cloud-init. See LICENSE file for license information.

"""NoCloud KVM Image Base Class."""

from tests.cloud_tests.images import base
from tests.cloud_tests.snapshots import nocloudkvm as nocloud_kvm_snapshot


class NoCloudKVMImage(base.Image):
    """NoCloud KVM backed image."""

    platform_name = "nocloud-kvm"

    def __init__(self, platform, config, img_path):
        """Set up image.

        @param platform: platform object
        @param config: image configuration
        @param img_path: path to the image
        """
        self.modified = False
        self._instance = None
        self._img_path = img_path

        super(NoCloudKVMImage, self).__init__(platform, config)

    @property
    def instance(self):
        """Returns an instance of an image."""
        if not self._instance:
            if not self._img_path:
                raise RuntimeError()

            self._instance = self.platform.create_image(
                self.properties, self.config, self.features, self._img_path,
                image_desc=str(self), use_desc='image-modification')
        return self._instance

    @property
    def properties(self):
        """Dictionary containing: 'arch', 'os', 'version', 'release'."""
        return {
            'arch': self.config['arch'],
            'os': self.config['family'],
            'release': self.config['release'],
            'version': self.config['version'],
        }

    def execute(self, *args, **kwargs):
        """Execute command in image, modifying image."""
        return self.instance.execute(*args, **kwargs)

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'."""
        return self.instance.push_file(local_path, remote_path)

    def run_script(self, *args, **kwargs):
        """Run script in image, modifying image.

        @return_value: script output
        """
        return self.instance.run_script(*args, **kwargs)

    def snapshot(self):
        """Create snapshot of image, block until done."""
        if not self._img_path:
            raise RuntimeError()

        instance = self.platform.create_image(
            self.properties, self.config, self.features,
            self._img_path, image_desc=str(self), use_desc='snapshot')

        return nocloud_kvm_snapshot.NoCloudKVMSnapshot(
            self.platform, self.properties, self.config,
            self.features, instance)

    def destroy(self):
        """Unset path to signal image is no longer used.

        The removal of the images and all other items is handled by the
        framework. In some cases we want to keep the images, so let the
        framework decide whether to keep or destroy everything.
        """
        self._img_path = None
        self._instance.destroy()
        super(NoCloudKVMImage, self).destroy()

# vi: ts=4 expandtab
