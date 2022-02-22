# This file is part of cloud-init. See LICENSE file for license information.

""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os
import shutil
import tempfile
from contextlib import ExitStack
from unittest import mock
from unittest.mock import call

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from cloudinit.distros.debian import Distro
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud

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

EXPECTED_BASE_CONTENT = """
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
"""

EXPECTED_MIRROR_CONTENT = """
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-security main restricted
"""

EXPECTED_PRIMSEC_CONTENT = """
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
"""


class TestAptSourceConfigSourceList(t_help.FilesystemMockingTestCase):
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""

    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.subp = subp.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

        rpatcher = mock.patch("cloudinit.util.lsb_release")
        get_rel = rpatcher.start()
        get_rel.return_value = {"codename": "fakerel"}
        self.addCleanup(rpatcher.stop)
        apatcher = mock.patch("cloudinit.util.get_dpkg_architecture")
        get_arch = apatcher.start()
        get_arch.return_value = "amd64"
        self.addCleanup(apatcher.stop)

    def _apt_source_list(self, distro, cfg, cfg_on_empty=False):
        """_apt_source_list - Test rendering from template (generic)"""
        # entry at top level now, wrap in 'apt' key
        cfg = {"apt": cfg}
        mycloud = get_cloud(distro)

        with ExitStack() as stack:
            mock_writefile = stack.enter_context(
                mock.patch.object(util, "write_file")
            )
            mock_loadfile = stack.enter_context(
                mock.patch.object(
                    util, "load_file", return_value=MOCKED_APT_SRC_LIST
                )
            )
            mock_isfile = stack.enter_context(
                mock.patch.object(os.path, "isfile", return_value=True)
            )
            stack.enter_context(mock.patch.object(util, "del_file"))
            cfg_func = (
                "cloudinit.config.cc_apt_configure."
                "_should_configure_on_empty_apt"
            )
            mock_shouldcfg = stack.enter_context(
                mock.patch(cfg_func, return_value=(cfg_on_empty, "test"))
            )
            cc_apt_configure.handle("test", cfg, mycloud, LOG, None)

            return mock_writefile, mock_loadfile, mock_isfile, mock_shouldcfg

    def test_apt_v3_source_list_debian(self):
        """test_apt_v3_source_list_debian - without custom sources or parms"""
        cfg = {}
        distro = "debian"
        expected = EXPECTED_BASE_CONTENT

        (
            mock_writefile,
            mock_load_file,
            mock_isfile,
            mock_shouldcfg,
        ) = self._apt_source_list(distro, cfg, cfg_on_empty=True)

        template = "/etc/cloud/templates/sources.list.%s.tmpl" % distro
        mock_writefile.assert_called_once_with(
            "/etc/apt/sources.list", expected, mode=0o644
        )
        mock_load_file.assert_called_with(template)
        mock_isfile.assert_any_call(template)
        self.assertEqual(1, mock_shouldcfg.call_count)

    def test_apt_v3_source_list_ubuntu(self):
        """test_apt_v3_source_list_ubuntu - without custom sources or parms"""
        cfg = {}
        distro = "ubuntu"
        expected = EXPECTED_BASE_CONTENT

        (
            mock_writefile,
            mock_load_file,
            mock_isfile,
            mock_shouldcfg,
        ) = self._apt_source_list(distro, cfg, cfg_on_empty=True)

        template = "/etc/cloud/templates/sources.list.%s.tmpl" % distro
        mock_writefile.assert_called_once_with(
            "/etc/apt/sources.list", expected, mode=0o644
        )
        mock_load_file.assert_called_with(template)
        mock_isfile.assert_any_call(template)
        self.assertEqual(1, mock_shouldcfg.call_count)

    def test_apt_v3_source_list_ubuntu_snappy(self):
        """test_apt_v3_source_list_ubuntu_snappy - without custom sources or
        parms"""
        cfg = {"apt": {}}
        mycloud = get_cloud()

        with mock.patch.object(util, "write_file") as mock_writefile:
            with mock.patch.object(
                util, "system_is_snappy", return_value=True
            ) as mock_issnappy:
                cc_apt_configure.handle("test", cfg, mycloud, LOG, None)

        self.assertEqual(0, mock_writefile.call_count)
        self.assertEqual(1, mock_issnappy.call_count)

    def test_apt_v3_source_list_centos(self):
        """test_apt_v3_source_list_centos - without custom sources or parms"""
        cfg = {}
        distro = "rhel"

        mock_writefile, _, _, _ = self._apt_source_list(distro, cfg)

        self.assertEqual(0, mock_writefile.call_count)

    def test_apt_v3_source_list_psm(self):
        """test_apt_v3_source_list_psm - Test specifying prim+sec mirrors"""
        pm = "http://test.ubuntu.com/ubuntu/"
        sm = "http://testsec.ubuntu.com/ubuntu/"
        cfg = {
            "preserve_sources_list": False,
            "primary": [{"arches": ["default"], "uri": pm}],
            "security": [{"arches": ["default"], "uri": sm}],
        }
        distro = "ubuntu"
        expected = EXPECTED_PRIMSEC_CONTENT

        mock_writefile, mock_load_file, mock_isfile, _ = self._apt_source_list(
            distro, cfg, cfg_on_empty=True
        )

        template = "/etc/cloud/templates/sources.list.%s.tmpl" % distro
        mock_writefile.assert_called_once_with(
            "/etc/apt/sources.list", expected, mode=0o644
        )
        mock_load_file.assert_called_with(template)
        mock_isfile.assert_any_call(template)

    def test_apt_v3_srcl_custom(self):
        """test_apt_v3_srcl_custom - Test rendering a custom source template"""
        cfg = util.load_yaml(YAML_TEXT_CUSTOM_SL)
        mycloud = get_cloud()

        # the second mock restores the original subp
        with mock.patch.object(util, "write_file") as mockwrite:
            with mock.patch.object(subp, "subp", self.subp):
                with mock.patch.object(
                    Distro, "get_primary_arch", return_value="amd64"
                ):
                    cc_apt_configure.handle(
                        "notimportant", cfg, mycloud, LOG, None
                    )

        calls = [
            call(
                "/etc/apt/sources.list", EXPECTED_CONVERTED_CONTENT, mode=0o644
            )
        ]
        mockwrite.assert_has_calls(calls)


# vi: ts=4 expandtab
