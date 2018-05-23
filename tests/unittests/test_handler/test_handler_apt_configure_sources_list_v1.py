# This file is part of cloud-init. See LICENSE file for license information.

""" test_handler_apt_configure_sources_list
Test templating of sources list
"""
import logging
import os
import shutil
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import templater
from cloudinit import util

from cloudinit.config import cc_apt_configure
from cloudinit.sources import DataSourceNone

from cloudinit.distros.debian import Distro

from cloudinit.tests import helpers as t_help

LOG = logging.getLogger(__name__)

YAML_TEXT_CUSTOM_SL = """
apt_mirror: http://archive.ubuntu.com/ubuntu/
apt_custom_sources_list: |
    ## template:jinja
    ## Note, this file is written by cloud-init on first boot of an instance
    ## modifications made here will not survive a re-bundle.
    ## if you wish to make changes you can:
    ## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
    ##     or do the same in user-data
    ## b.) add sources in /etc/apt/sources.list.d
    ## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

    # See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
    # newer versions of the distribution.
    deb {{mirror}} {{codename}} main restricted
    deb-src {{mirror}} {{codename}} main restricted
    # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = (
    """## Note, this file is written by cloud-init on first boot of an instance
## modifications made here will not survive a re-bundle.
## if you wish to make changes you can:
## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
##     or do the same in user-data
## b.) add sources in /etc/apt/sources.list.d
## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
deb-src http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
# FIND_SOMETHING_SPECIAL
""")


class TestAptSourceConfigSourceList(t_help.FilesystemMockingTestCase):
    """TestAptSourceConfigSourceList
    Main Class to test sources list rendering
    """
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.subp = util.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

        rpatcher = mock.patch("cloudinit.util.lsb_release")
        get_rel = rpatcher.start()
        get_rel.return_value = {'codename': "fakerelease"}
        self.addCleanup(rpatcher.stop)
        apatcher = mock.patch("cloudinit.util.get_architecture")
        get_arch = apatcher.start()
        get_arch.return_value = 'amd64'
        self.addCleanup(apatcher.stop)

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    def apt_source_list(self, distro, mirror, mirrorcheck=None):
        """apt_source_list
        Test rendering of a source.list from template for a given distro
        """
        if mirrorcheck is None:
            mirrorcheck = mirror

        if isinstance(mirror, list):
            cfg = {'apt_mirror_search': mirror}
        else:
            cfg = {'apt_mirror': mirror}
        mycloud = self._get_cloud(distro)

        with mock.patch.object(util, 'write_file') as mockwf:
            with mock.patch.object(util, 'load_file',
                                   return_value="faketmpl") as mocklf:
                with mock.patch.object(os.path, 'isfile',
                                       return_value=True) as mockisfile:
                    with mock.patch.object(templater, 'render_string',
                                           return_value="fake") as mockrnd:
                        with mock.patch.object(util, 'rename'):
                            cc_apt_configure.handle("test", cfg, mycloud,
                                                    LOG, None)

        mockisfile.assert_any_call(
            ('/etc/cloud/templates/sources.list.%s.tmpl' % distro))
        mocklf.assert_any_call(
            ('/etc/cloud/templates/sources.list.%s.tmpl' % distro))
        mockrnd.assert_called_once_with('faketmpl',
                                        {'RELEASE': 'fakerelease',
                                         'PRIMARY': mirrorcheck,
                                         'MIRROR': mirrorcheck,
                                         'SECURITY': mirrorcheck,
                                         'codename': 'fakerelease',
                                         'primary': mirrorcheck,
                                         'mirror': mirrorcheck,
                                         'security': mirrorcheck})
        mockwf.assert_called_once_with('/etc/apt/sources.list', 'fake',
                                       mode=0o644)

    def test_apt_v1_source_list_debian(self):
        """Test rendering of a source.list from template for debian"""
        self.apt_source_list('debian', 'http://httpredir.debian.org/debian')

    def test_apt_v1_source_list_ubuntu(self):
        """Test rendering of a source.list from template for ubuntu"""
        self.apt_source_list('ubuntu', 'http://archive.ubuntu.com/ubuntu/')

    @staticmethod
    def myresolve(name):
        """Fake util.is_resolvable for mirrorfail tests"""
        if name == "does.not.exist":
            print("Faking FAIL for '%s'" % name)
            return False
        else:
            print("Faking SUCCESS for '%s'" % name)
            return True

    def test_apt_v1_srcl_debian_mirrorfail(self):
        """Test rendering of a source.list from template for debian"""
        with mock.patch.object(util, 'is_resolvable',
                               side_effect=self.myresolve) as mockresolve:
            self.apt_source_list('debian',
                                 ['http://does.not.exist',
                                  'http://httpredir.debian.org/debian'],
                                 'http://httpredir.debian.org/debian')
        mockresolve.assert_any_call("does.not.exist")
        mockresolve.assert_any_call("httpredir.debian.org")

    def test_apt_v1_srcl_ubuntu_mirrorfail(self):
        """Test rendering of a source.list from template for ubuntu"""
        with mock.patch.object(util, 'is_resolvable',
                               side_effect=self.myresolve) as mockresolve:
            self.apt_source_list('ubuntu',
                                 ['http://does.not.exist',
                                  'http://archive.ubuntu.com/ubuntu/'],
                                 'http://archive.ubuntu.com/ubuntu/')
        mockresolve.assert_any_call("does.not.exist")
        mockresolve.assert_any_call("archive.ubuntu.com")

    def test_apt_v1_srcl_custom(self):
        """Test rendering from a custom source.list template"""
        cfg = util.load_yaml(YAML_TEXT_CUSTOM_SL)
        mycloud = self._get_cloud('ubuntu')

        # the second mock restores the original subp
        with mock.patch.object(util, 'write_file') as mockwrite:
            with mock.patch.object(util, 'subp', self.subp):
                with mock.patch.object(Distro, 'get_primary_arch',
                                       return_value='amd64'):
                    cc_apt_configure.handle("notimportant", cfg, mycloud,
                                            LOG, None)

        mockwrite.assert_called_once_with(
            '/etc/apt/sources.list',
            EXPECTED_CONVERTED_CONTENT,
            mode=420)


# vi: ts=4 expandtab
