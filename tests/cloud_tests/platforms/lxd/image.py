# This file is part of cloud-init. See LICENSE file for license information.

"""LXD Image Base Class."""

import os
import shutil
import tempfile

from ..images import Image
from .snapshot import LXDSnapshot
from cloudinit import util as c_util
from tests.cloud_tests import util


class LXDImage(Image):
    """LXD backed image."""

    platform_name = "lxd"

    def __init__(self, platform, config, pylxd_image):
        """Set up image.

        @param platform: platform object
        @param config: image configuration
        """
        self.modified = False
        self._img_instance = None
        self._pylxd_image = None
        self.pylxd_image = pylxd_image
        super(LXDImage, self).__init__(platform, config)

    @property
    def pylxd_image(self):
        """Property function."""
        if self._pylxd_image:
            self._pylxd_image.sync()
        return self._pylxd_image

    @pylxd_image.setter
    def pylxd_image(self, pylxd_image):
        if self._img_instance:
            self._instance.destroy()
            self._img_instance = None
        if (self._pylxd_image and
                (self._pylxd_image is not pylxd_image) and
                (not self.config.get('cache_base_image') or self.modified)):
            self._pylxd_image.delete(wait=True)
        self.modified = False
        self._pylxd_image = pylxd_image

    @property
    def _instance(self):
        """Internal use only, returns a instance

        This starts an lxc instance from the image, so it is "dirty".
        Better would be some way to modify this "at rest".
        lxc-pstart would be an option."""
        if not self._img_instance:
            self._img_instance = self.platform.launch_container(
                self.properties, self.config, self.features,
                use_desc='image-modification', image_desc=str(self),
                image=self.pylxd_image.fingerprint)
            self._img_instance.start()
        return self._img_instance

    @property
    def properties(self):
        """{} containing: 'arch', 'os', 'version', 'release'."""
        properties = self.pylxd_image.properties
        return {
            'arch': properties.get('architecture'),
            'os': properties.get('os'),
            'version': properties.get('version'),
            'release': properties.get('release'),
        }

    def export_image(self, output_dir):
        """Export image from lxd image store to (split) tarball on disk.

        @param output_dir: dir to store tarballs in
        @return_value: tuple of path to metadata tarball and rootfs tarball
        """
        # pylxd's image export feature doesn't do split exports, so use cmdline
        c_util.subp(['lxc', 'image', 'export', self.pylxd_image.fingerprint,
                     output_dir], capture=True)
        tarballs = [p for p in os.listdir(output_dir) if p.endswith('tar.xz')]
        metadata = os.path.join(
            output_dir, next(p for p in tarballs if p.startswith('meta-')))
        rootfs = os.path.join(
            output_dir, next(p for p in tarballs if not p.startswith('meta-')))
        return (metadata, rootfs)

    def import_image(self, metadata, rootfs):
        """Import image to lxd image store from (split) tarball on disk.

        Note, this will replace and delete the current pylxd_image

        @param metadata: metadata tarball
        @param rootfs: rootfs tarball
        @return_value: imported image fingerprint
        """
        alias = util.gen_instance_name(
            image_desc=str(self), use_desc='update-metadata')
        c_util.subp(['lxc', 'image', 'import', metadata, rootfs,
                     '--alias', alias], capture=True)
        self.pylxd_image = self.platform.query_image_by_alias(alias)
        return self.pylxd_image.fingerprint

    def update_templates(self, template_config, template_data):
        """Update the image's template configuration.

        Note, this will replace and delete the current pylxd_image

        @param template_config: config overrides for template metadata
        @param template_data: template data to place into templates/
        """
        # set up tmp files
        export_dir = tempfile.mkdtemp(prefix='cloud_test_util_')
        extract_dir = tempfile.mkdtemp(prefix='cloud_test_util_')
        new_metadata = os.path.join(export_dir, 'new-meta.tar.xz')
        metadata_yaml = os.path.join(extract_dir, 'metadata.yaml')
        template_dir = os.path.join(extract_dir, 'templates')

        try:
            # extract old data
            (metadata, rootfs) = self.export_image(export_dir)
            shutil.unpack_archive(metadata, extract_dir)

            # update metadata
            metadata = c_util.read_conf(metadata_yaml)
            templates = metadata.get('templates', {})
            templates.update(template_config)
            metadata['templates'] = templates
            util.yaml_dump(metadata, metadata_yaml)

            # write out template files
            for name, content in template_data.items():
                path = os.path.join(template_dir, name)
                c_util.write_file(path, content)

            # store new data, mark new image as modified
            util.flat_tar(new_metadata, extract_dir)
            self.import_image(new_metadata, rootfs)
            self.modified = True

        finally:
            # remove tmpfiles
            shutil.rmtree(export_dir)
            shutil.rmtree(extract_dir)

    def _execute(self, *args, **kwargs):
        """Execute command in image, modifying image."""
        return self._instance._execute(*args, **kwargs)

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'."""
        return self._instance.push_file(local_path, remote_path)

    def run_script(self, *args, **kwargs):
        """Run script in image, modifying image.

        @return_value: script output
        """
        return self._instance.run_script(*args, **kwargs)

    def snapshot(self):
        """Create snapshot of image, block until done."""
        # get empty user data to pass in to instance
        # if overrides for user data provided, use them
        empty_userdata = util.update_user_data(
            {}, self.config.get('user_data_overrides', {}))
        conf = {'user.user-data': empty_userdata}
        # clone current instance
        instance = self.platform.launch_container(
            self.properties, self.config, self.features,
            container=self._instance.name, image_desc=str(self),
            use_desc='snapshot', container_config=conf)
        # wait for cloud-init before boot_clean_script is run to ensure
        # /var/lib/cloud is removed cleanly
        instance.start(wait=True, wait_for_cloud_init=True)
        if self.config.get('boot_clean_script'):
            instance.run_script(self.config.get('boot_clean_script'))
        # freeze current instance and return snapshot
        instance.freeze()
        return LXDSnapshot(self.platform, self.properties, self.config,
                           self.features, instance)

    def destroy(self):
        """Clean up data associated with image."""
        self.pylxd_image = None
        super(LXDImage, self).destroy()

# vi: ts=4 expandtab
