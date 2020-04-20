# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD snapshot."""

from ..snapshots import Snapshot


class LXDSnapshot(Snapshot):
    """LXD image copy backed snapshot."""

    platform_name = "lxd"

    def __init__(self, platform, properties, config, features,
                 pylxd_frozen_instance):
        """Set up snapshot.

        @param platform: platform object
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        self.pylxd_frozen_instance = pylxd_frozen_instance
        super(LXDSnapshot, self).__init__(
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
        inst_config = {'user.user-data': user_data}
        if meta_data:
            inst_config['user.meta-data'] = meta_data
        instance = self.platform.launch_container(
            self.properties, self.config, self.features, block=block,
            image_desc=str(self), container=self.pylxd_frozen_instance.name,
            use_desc=use_desc, container_config=inst_config)
        if start:
            instance.start()
        return instance

    def destroy(self):
        """Clean up snapshot data."""
        self.pylxd_frozen_instance.destroy()
        super(LXDSnapshot, self).destroy()

# vi: ts=4 expandtab
