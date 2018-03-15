# This file is part of cloud-init. See LICENSE file for license information.

"""Base NoCloud KVM platform."""
import glob
import os

from simplestreams import filters
from simplestreams import mirrors
from simplestreams import objectstores
from simplestreams import util as s_util

from ..platforms import Platform
from .image import NoCloudKVMImage
from .instance import NoCloudKVMInstance
from cloudinit import util as c_util
from tests.cloud_tests import util


class NoCloudKVMPlatform(Platform):
    """NoCloud KVM test platform."""

    platform_name = 'nocloud-kvm'

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        (url, path) = s_util.path_from_mirror_url(img_conf['mirror_url'], None)

        filter = filters.get_filters(['arch=%s' % c_util.get_architecture(),
                                      'release=%s' % img_conf['release'],
                                      'ftype=disk1.img'])
        mirror_config = {'filters': filter,
                         'keep_items': False,
                         'max_items': 1,
                         'checksumming_reader': True,
                         'item_download': True
                         }

        def policy(content, path):
            return s_util.read_signed(content, keyring=img_conf['keyring'])

        smirror = mirrors.UrlMirrorReader(url, policy=policy)
        tstore = objectstores.FileStore(img_conf['mirror_dir'])
        tmirror = mirrors.ObjectFilterMirror(config=mirror_config,
                                             objectstore=tstore)
        tmirror.sync(smirror, path)

        search_d = os.path.join(img_conf['mirror_dir'], '**',
                                img_conf['release'], '**', '*.img')

        images = []
        for fname in glob.iglob(search_d, recursive=True):
            images.append(fname)

        if len(images) < 1:
            raise RuntimeError("No images found under '%s'" % search_d)
        if len(images) > 1:
            raise RuntimeError(
                "Multiple images found in '%s': %s" % (search_d,
                                                       ' '.join(images)))

        image = NoCloudKVMImage(self, img_conf, images[0])
        return image

    def create_instance(self, properties, config, features,
                        src_img_path, image_desc=None, use_desc=None,
                        user_data=None, meta_data=None):
        """Create an instance

        @param src_img_path: image path to launch from
        @param properties: image properties
        @param config: image configuration
        @param features: image features
        @param image_desc: description of image being launched
        @param use_desc: description of container's use
        @return_value: cloud_tests.instances instance
        """
        name = util.gen_instance_name(image_desc=image_desc, use_desc=use_desc)
        img_path = os.path.join(self.config['data_dir'], name + '.qcow2')
        c_util.subp(['qemu-img', 'create', '-f', 'qcow2',
                    '-b', src_img_path, img_path])

        return NoCloudKVMInstance(self, name, img_path, properties, config,
                                  features, user_data, meta_data)

# vi: ts=4 expandtab
