# This file is part of cloud-init. See LICENSE file for license information.

""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os
import shutil
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock
from mock import call

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.config import cc_apt_configure
from cloudinit.sources import DataSourceNone

from cloudinit.distros.debian import Distro

from .. import helpers as t_help

LOG = logging.getLogger(__name__)

TARGET = "/"

# Input and expected output for the custom template
YAML_TEXT_CUSTOM_SL = """
apt:
  primary:
    - arches: [default]
      uri: http://test.ubuntu.com/ubuntu/
  security:
    - arches: [default]
      uri: http://testsec.ubuntu.com/ubuntu/
  sources_list: |

      # Note, this file is written by cloud-init at install time. It should not
      # end up on the installed system itself.
      # See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
      # newer versions of the distribution.
      deb $MIRROR $RELEASE main restricted
      deb-src $MIRROR $RELEASE main restricted
      deb $PRIMARY $RELEASE universe restricted
      deb $SECURITY $RELEASE-security multiverse
      # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = """
# Note, this file is written by cloud-init at install time. It should not
# end up on the installed system itself.
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel universe restricted
deb http://testsec.ubuntu.com/ubuntu/ fakerel-security multiverse
# FIND_SOMETHING_SPECIAL
"""

# mocked to be independent to the unittest system
MOCKED_APT_SRC_LIST = """
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
"""

EXPECTED_BASE_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
""")

EXPECTED_MIRROR_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-security main restricted
""")

EXPECTED_PRIMSEC_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
""")


class TestAptSourceConfigSourceList(t_help.FilesystemMockingTestCase):
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.subp = util.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

        rpatcher = mock.patch("cloudinit.util.lsb_release")
        get_rel = rpatcher.start()
        get_rel.return_value = {'codename': "fakerel"}
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

    def _apt_source_list(self, cfg, expected, distro):
        "_apt_source_list - Test rendering from template (generic)"

        # entry at top level now, wrap in 'apt' key
        cfg = {'apt': cfg}
        mycloud = self._get_cloud(distro)
        with mock.patch.object(util, 'write_file') as mockwf:
            with mock.patch.object(util, 'load_file',
                                   return_value=MOCKED_APT_SRC_LIST) as mocklf:
                with mock.patch.object(os.path, 'isfile',
                                       return_value=True) as mockisfile:
                    with mock.patch.object(util, 'rename'):
                        cc_apt_configure.handle("test", cfg, mycloud,
                                                LOG, None)

        # check if it would have loaded the distro template
        mockisfile.assert_any_call(
            ('/etc/cloud/templates/sources.list.%s.tmpl' % distro))
        mocklf.assert_any_call(
            ('/etc/cloud/templates/sources.list.%s.tmpl' % distro))
        # check expected content in result
        mockwf.assert_called_once_with('/etc/apt/sources.list', expected,
                                       mode=0o644)

    def test_apt_v3_source_list_debian(self):
        """test_apt_v3_source_list_debian - without custom sources or parms"""
        cfg = {}
        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT, 'debian')

    def test_apt_v3_source_list_ubuntu(self):
        """test_apt_v3_source_list_ubuntu - without custom sources or parms"""
        cfg = {}
        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT, 'ubuntu')

    def test_apt_v3_source_list_psm(self):
        """test_apt_v3_source_list_psm - Test specifying prim+sec mirrors"""
        pm = 'http://test.ubuntu.com/ubuntu/'
        sm = 'http://testsec.ubuntu.com/ubuntu/'
        cfg = {'preserve_sources_list': False,
               'primary': [{'arches': ["default"],
                            'uri': pm}],
               'security': [{'arches': ["default"],
                             'uri': sm}]}

        self._apt_source_list(cfg, EXPECTED_PRIMSEC_CONTENT, 'ubuntu')

    def test_apt_v3_srcl_custom(self):
        """test_apt_v3_srcl_custom - Test rendering a custom source template"""
        cfg = util.load_yaml(YAML_TEXT_CUSTOM_SL)
        mycloud = self._get_cloud('ubuntu')

        # the second mock restores the original subp
        with mock.patch.object(util, 'write_file') as mockwrite:
            with mock.patch.object(util, 'subp', self.subp):
                with mock.patch.object(Distro, 'get_primary_arch',
                                       return_value='amd64'):
                    cc_apt_configure.handle("notimportant", cfg, mycloud,
                                            LOG, None)

        calls = [call('/etc/apt/sources.list',
                      EXPECTED_CONVERTED_CONTENT,
                      mode=0o644)]
        mockwrite.assert_has_calls(calls)


# vi: ts=4 expandtab
