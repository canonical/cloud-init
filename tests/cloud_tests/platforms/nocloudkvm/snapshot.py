# This file is part of cloud-init. See LICENSE file for license information.

"""Base NoCloud KVM snapshot."""
import os
import shutil
import tempfile

from ..snapshots import Snapshot


class NoCloudKVMSnapshot(Snapshot):
    """NoCloud KVM image copy backed snapshot."""

    platform_name = "nocloud-kvm"

    def __init__(self, platform, properties, config, features, image_path):
        """Set up snapshot.

        @param platform: platform object
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        @param image_path: image file to snapshot.
        """
        self._workd = tempfile.mkdtemp(prefix='NoCloudKVMSnapshot')
        snapshot = os.path.join(self._workd, 'snapshot')
        shutil.copyfile(image_path, snapshot)
        self._image_path = snapshot

        super(NoCloudKVMSnapshot, self).__init__(
            platform, properties, config, features)

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
        instance = self.platform.create_instance(
            self.properties, self.config, self.features,
            self._image_path, image_desc=str(self), use_desc=use_desc,
            user_data=user_data, meta_data=meta_data)

        if start:
            instance.start()

        return instance

    def destroy(self):
        """Clean up snapshot data."""
        shutil.rmtree(self._workd)
        super(NoCloudKVMSnapshot, self).destroy()

# vi: ts=4 expandtab
