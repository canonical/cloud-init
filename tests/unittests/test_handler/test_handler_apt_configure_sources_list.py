""" test_handler_apt_configure_sources_list
Test templating of sources list
"""
import os
import shutil
import tempfile
import re

import logging

try:
    from unittest import mock
except ImportError:
    import mock

from cloudinit import cloud
from cloudinit import distros
from cloudinit import util
from cloudinit import helpers
from cloudinit import templater

from cloudinit.sources import DataSourceNone
from cloudinit.config import cc_apt_configure

from .. import helpers as t_help

LOG = logging.getLogger(__name__)


def load_tfile_or_url(*args, **kwargs):
    """ load_tfile_or_url
    load file and return content after decoding
    """
    return util.decode_binary(util.read_file_or_url(*args, **kwargs).contents)


class TestAptSourceConfigSourceList(t_help.FilesystemMockingTestCase):
    """ TestAptSourceConfigSourceList
    Main Class to test sources list rendering
    """
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, paths, {}, mydist, None)

# TODO - Ubuntu template
# TODO - Debian template
# TODO Later - custom template filename
# TODO Later - custom template raw

    def test_apt_source_list_ubuntu(self):
        """ test_apt_source_list
        Test rendering of a source.list from template for ubuntu
        """
        self.patchOS(self.new_root)
        self.patchUtils(self.new_root)

        cfg = {'apt_mirror': 'http://archive.ubuntu.com/ubuntu/'}
        mycloud = self._get_cloud('ubuntu')

        with mock.patch.object(templater, 'render_to_file') as mocktmpl:
            with mock.patch.object(os.path, 'isfile',
                                   return_value=True) as mockisfile:
                cc_apt_configure.handle("notimportant", cfg, mycloud,
                                        LOG, None)

        mockisfile.assert_any_call(('/etc/cloud/templates/'
                                    'sources.list.ubuntu.tmpl'))
        mocktmpl.assert_called_once_with(('/etc/cloud/templates/'
                                          'sources.list.ubuntu.tmpl'),
                                         '/etc/apt/sources.list',
                                         {'codename': '',
                                          'primary':
                                          'http://archive.ubuntu.com/ubuntu/',
                                          'mirror':
                                          'http://archive.ubuntu.com/ubuntu/'})


# vi: ts=4 expandtab
