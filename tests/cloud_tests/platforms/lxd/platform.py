# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD platform."""

from pylxd import (Client, exceptions)

from ..platforms import Platform
from .image import LXDImage
from .instance import LXDInstance
from tests.cloud_tests import util

DEFAULT_SSTREAMS_SERVER = "https://images.linuxcontainers.org:8443"


class LXDPlatform(Platform):
    """LXD test platform."""

    platform_name = 'lxd'

    def __init__(self, config):
        """Set up platform."""
        super(LXDPlatform, self).__init__(config)
        # TODO: allow configuration of remote lxd host via env variables
        # set up lxd connection
        self.client = Client()

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        pylxd_image = self.client.images.create_from_simplestreams(
            img_conf.get('sstreams_server', DEFAULT_SSTREAMS_SERVER),
            img_conf['alias'])
        image = LXDImage(self, img_conf, pylxd_image)
        if img_conf.get('override_templates', False):
            image.update_templates(self.config.get('template_overrides', {}),
                                   self.config.get('template_files', {}))
        return image

    def launch_container(self, properties, config, features,
                         image=None, container=None, ephemeral=False,
                         container_config=None, block=True, image_desc=None,
                         use_desc=None):
        """Launch a container.

        @param properties: image properties
        @param config: image configuration
        @param features: image features
        @param image: image fingerprint to launch from
        @param container: container to copy
        @param ephemeral: delete image after first shutdown
        @param container_config: config options for instance as dict
        @param block: wait until container created
        @param image_desc: description of image being launched
        @param use_desc: description of container's use
        @return_value: cloud_tests.instances instance
        """
        if not (image or container):
            raise ValueError("either image or container must be specified")
        container = self.client.containers.create({
            'name': util.gen_instance_name(image_desc=image_desc,
                                           use_desc=use_desc,
                                           used_list=self.list_containers()),
            'ephemeral': bool(ephemeral),
            'config': (container_config
                       if isinstance(container_config, dict) else {}),
            'source': ({'type': 'image', 'fingerprint': image} if image else
                       {'type': 'copy', 'source': container})
        }, wait=block)
        return LXDInstance(self, container.name, properties, config, features,
                           container)

    def container_exists(self, container_name):
        """Check if container with name 'container_name' exists.

        @return_value: True if exists else False
        """
        res = True
        try:
            self.client.containers.get(container_name)
        except exceptions.LXDAPIException as e:
            res = False
            if e.response.status_code != 404:
                raise
        return res

    def list_containers(self):
        """List names of all containers.

        @return_value: list of names
        """
        return [container.name for container in self.client.containers.all()]

    def query_image_by_alias(self, alias):
        """Get image by alias in local image store.

        @param alias: alias of image
        @return_value: pylxd image (not cloud_tests.images instance)
        """
        return self.client.images.get_by_alias(alias)

# vi: ts=4 expandtab
