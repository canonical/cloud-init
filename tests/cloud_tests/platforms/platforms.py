# This file is part of cloud-init. See LICENSE file for license information.

"""Base platform class."""
import os
import shutil

from simplestreams import filters, mirrors
from simplestreams import util as s_util

from cloudinit import util as c_util

from tests.cloud_tests import util


class Platform(object):
    """Base class for platforms."""

    platform_name = None

    def __init__(self, config):
        """Set up platform."""
        self.config = config
        self.tmpdir = util.mkdtemp()
        if 'data_dir' in config:
            self.data_dir = config['data_dir']
        else:
            self.data_dir = os.path.join(self.tmpdir, "data_dir")
            os.mkdir(self.data_dir)

        self._generate_ssh_keys(self.data_dir)

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        raise NotImplementedError

    def destroy(self):
        """Clean up platform data."""
        shutil.rmtree(self.tmpdir)

    def _generate_ssh_keys(self, data_dir):
        """Generate SSH keys to be used with image."""
        filename = os.path.join(data_dir, self.config['private_key'])

        if os.path.exists(filename):
            c_util.del_file(filename)

        c_util.subp(['ssh-keygen', '-t', 'rsa', '-b', '4096',
                     '-f', filename, '-P', '',
                     '-C', 'ubuntu@cloud_test'],
                    capture=True)

    @staticmethod
    def _query_streams(img_conf, img_filter):
        """Query streams for latest image given a specific filter.

        @param img_conf: configuration for image
        @param filters: array of filters as strings format 'key=value'
        @return: dictionary with latest image information or empty
        """
        def policy(content, path):
            return s_util.read_signed(content, keyring=img_conf['keyring'])

        (url, path) = s_util.path_from_mirror_url(img_conf['mirror_url'], None)
        smirror = mirrors.UrlMirrorReader(url, policy=policy)

        config = {'max_items': 1, 'filters': filters.get_filters(img_filter)}
        tmirror = FilterMirror(config)
        tmirror.sync(smirror, path)

        try:
            return tmirror.json_entries[0]
        except IndexError:
            raise RuntimeError('no images found with filter: %s' % img_filter)


class FilterMirror(mirrors.BasicMirrorWriter):
    """Taken from sstream-query to return query result as json array."""

    def __init__(self, config=None):
        super(FilterMirror, self).__init__(config=config)
        if config is None:
            config = {}
        self.config = config
        self.filters = config.get('filters', [])
        self.json_entries = []

    def load_products(self, path=None, content_id=None):
        return {'content_id': content_id, 'products': {}}

    def filter_item(self, data, src, target, pedigree):
        return filters.filter_item(self.filters, data, src, pedigree)

    def insert_item(self, data, src, target, pedigree, contentsource):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]['items'][ped[2]]
        # contentsource is a ContentSource if 'path' exists in data or None
        data = s_util.products_exdata(src, pedigree)
        if 'path' in data:
            data.update({'item_url': contentsource.url})
        self.json_entries.append(data)

# vi: ts=4 expandtab
