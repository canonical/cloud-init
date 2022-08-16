# This file is part of cloud-init. See LICENSE file for license information.

""" test_apt_custom_mirrorlists
Test creation of mirrorlists
"""
import logging
import shutil
import tempfile
from contextlib import ExitStack
from unittest import mock
from unittest.mock import call

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestAptSourceConfigMirrorlists(t_help.FilesystemMockingTestCase):
    """TestAptSourceConfigMirrorlists - Class to test mirrorlists rendering"""

    def setUp(self):
        super().setUp()
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

    def test_apt_v3_mirrors_list(self):
        """test_apt_v3_mirrors_list"""
        cfg = {"apt": {"generate_mirrorlists": True}}

        mycloud = get_cloud("ubuntu")

        with ExitStack() as stack:
            mock_writefile = stack.enter_context(
                mock.patch.object(util, "write_file")
            )
            stack.enter_context(mock.patch.object(util, "ensure_dir"))
            cc_apt_configure.handle("test", cfg, mycloud, LOG, None)

        mock_writefile.assert_has_calls(
            [
                call(
                    "/etc/apt/mirrors/ubuntu.list",
                    "http://archive.ubuntu.com/ubuntu/\n",
                    mode=0o644,
                ),
                call(
                    "/etc/apt/mirrors/ubuntu-security.list",
                    "http://security.ubuntu.com/ubuntu/\n",
                    mode=0o644,
                ),
            ]
        )


# vi: ts=4 expandtab
