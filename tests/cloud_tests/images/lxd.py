# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests.images import base
from tests.cloud_tests.snapshots import lxd as lxd_snapshot


class LXDImage(base.Image):
    """
    LXD backed image
    """
    platform_name = "lxd"

    def __init__(self, name, config, platform, pylxd_image):
        """
        setup
        """
        self.platform = platform
        self._pylxd_image = pylxd_image
        self._instance = None
        super(LXDImage, self).__init__(name, config, platform)

    @property
    def pylxd_image(self):
        self._pylxd_image.sync()
        return self._pylxd_image

    @property
    def instance(self):
        if not self._instance:
            self._instance = self.platform.launch_container(
                image=self.pylxd_image.fingerprint,
                image_desc=str(self), use_desc='image-modification')
        self._instance.start(wait=True, wait_time=self.config.get('timeout'))
        return self._instance

    @property
    def properties(self):
        """
        {} containing: 'arch', 'os', 'version', 'release'
        """
        properties = self.pylxd_image.properties
        return {
            'arch': properties.get('architecture'),
            'os': properties.get('os'),
            'version': properties.get('version'),
            'release': properties.get('release'),
        }

    def execute(self, *args, **kwargs):
        """
        execute command in image, modifying image
        """
        return self.instance.execute(*args, **kwargs)

    def push_file(self, local_path, remote_path):
        """
        copy file at 'local_path' to instance at 'remote_path', modifying image
        """
        return self.instance.push_file(local_path, remote_path)

    def run_script(self, script):
        """
        run script in image, modifying image
        return_value: script output
        """
        return self.instance.run_script(script)

    def snapshot(self):
        """
        create snapshot of image, block until done
        """
        # clone current instance, start and freeze clone
        instance = self.platform.launch_container(
            container=self.instance.name, image_desc=str(self),
            use_desc='snapshot')
        instance.start(wait=True, wait_time=self.config.get('timeout'))
        if self.config.get('boot_clean_script'):
            instance.run_script(self.config.get('boot_clean_script'))
        instance.freeze()
        return lxd_snapshot.LXDSnapshot(
            self.properties, self.config, self.platform, instance)

    def destroy(self):
        """
        clean up data associated with image
        """
        if self._instance:
            self._instance.destroy()
        self.pylxd_image.delete(wait=True)
        super(LXDImage, self).destroy()

# vi: ts=4 expandtab
