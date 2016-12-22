# This file is part of cloud-init. See LICENSE file for license information.


class Snapshot(object):
    """
    Base class for snapshots
    """
    platform_name = None

    def __init__(self, properties, config):
        """
        Set up snapshot
        """
        self.properties = properties
        self.config = config

    def __str__(self):
        """
        a brief description of the snapshot
        """
        return '-'.join((self.properties['os'], self.properties['release']))

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
        raise NotImplementedError

    def destroy(self):
        """
        Clean up snapshot data
        """
        pass

# vi: ts=4 expandtab
