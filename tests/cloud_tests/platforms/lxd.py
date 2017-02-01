# This file is part of cloud-init. See LICENSE file for license information.

from pylxd import (Client, exceptions)

from tests.cloud_tests.images import lxd as lxd_image
from tests.cloud_tests.instances import lxd as lxd_instance
from tests.cloud_tests.platforms import base
from tests.cloud_tests import util

DEFAULT_SSTREAMS_SERVER = "https://images.linuxcontainers.org:8443"


class LXDPlatform(base.Platform):
    """
    Lxd test platform
    """
    platform_name = 'lxd'

    def __init__(self, config):
        """
        Set up platform
        """
        super(LXDPlatform, self).__init__(config)
        # TODO: allow configuration of remote lxd host via env variables
        # set up lxd connection
        self.client = Client()

    def get_image(self, img_conf):
        """
        Get image
        img_conf: dict containing config for image. platform_ident must have:
            alias: alias to use for simplestreams server
            sstreams_server: simplestreams server to use, or None for default
        return_value: cloud_tests.images instance
        """
        lxd_conf = self._extract_img_platform_config(img_conf)
        image = self.client.images.create_from_simplestreams(
            lxd_conf.get('sstreams_server', DEFAULT_SSTREAMS_SERVER),
            lxd_conf['alias'])
        return lxd_image.LXDImage(
            image.properties['description'], img_conf, self, image)

    def launch_container(self, image=None, container=None, ephemeral=False,
                         config=None, block=True,
                         image_desc=None, use_desc=None):
        """
        launch a container
        image: image fingerprint to launch from
        container: container to copy
        ephemeral: delete image after first shutdown
        config: config options for instance as dict
        block: wait until container created
        image_desc: description of image being launched
        use_desc: description of container's use
        return_value: cloud_tests.instances instance
        """
        if not (image or container):
            raise ValueError("either image or container must be specified")
        container = self.client.containers.create({
            'name': util.gen_instance_name(image_desc=image_desc,
                                           use_desc=use_desc,
                                           used_list=self.list_containers()),
            'ephemeral': bool(ephemeral),
            'config': config if isinstance(config, dict) else {},
            'source': ({'type': 'image', 'fingerprint': image} if image else
                       {'type': 'copy', 'source': container})
        }, wait=block)
        return lxd_instance.LXDInstance(container.name, self, container)

    def container_exists(self, container_name):
        """
        check if container with name 'container_name' exists
        return_value: True if exists else False
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
        """
        list names of all containers
        return_value: list of names
        """
        return [container.name for container in self.client.containers.all()]

    def destroy(self):
        """
        Clean up platform data
        """
        super(LXDPlatform, self).destroy()

# vi: ts=4 expandtab
