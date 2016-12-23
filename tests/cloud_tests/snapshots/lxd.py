# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests.snapshots import base


class LXDSnapshot(base.Snapshot):
    """
    LXD image copy backed snapshot
    """
    platform_name = "lxd"

    def __init__(self, properties, config, platform, pylxd_frozen_instance):
        """
        Set up snapshot
        """
        self.platform = platform
        self.pylxd_frozen_instance = pylxd_frozen_instance
        super(LXDSnapshot, self).__init__(properties, config)

    def launch(self, user_data, meta_data=None, block=True, start=True,
               use_desc=None):
        """
        launch instance

        user_data: user-data for the instance
        instance_id: instance-id for the instance
        block: wait until instance is created
        start: start instance and wait until fully started
        use_desc: description of snapshot instance use

        return_value: an Instance
        """
        inst_config = {'user.user-data': user_data}
        if meta_data:
            inst_config['user.meta-data'] = meta_data
        instance = self.platform.launch_container(
            container=self.pylxd_frozen_instance.name, config=inst_config,
            block=block, image_desc=str(self), use_desc=use_desc)
        if start:
            instance.start(wait=True, wait_time=self.config.get('timeout'))
        return instance

    def destroy(self):
        """
        Clean up snapshot data
        """
        self.pylxd_frozen_instance.destroy()
        super(LXDSnapshot, self).destroy()

# vi: ts=4 expandtab
