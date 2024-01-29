# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import shutil
import tempfile
from io import BytesIO

from configobj import ConfigObj

from cloudinit import util
from cloudinit.config import cc_timezone
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestTimezone(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestTimezone, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        self.patchUtils(self.new_root)
        self.patchOS(self.new_root)

    def test_set_timezone_sles(self):

        cfg = {
            "timezone": "Tatooine/Bestine",
        }
        cc = get_cloud("sles")

        # Create a dummy timezone file
        dummy_contents = "0123456789abcdefgh"
        util.write_file(
            "/usr/share/zoneinfo/%s" % cfg["timezone"], dummy_contents
        )

        cc_timezone.handle("cc_timezone", cfg, cc, [])

        contents = util.load_binary_file("/etc/sysconfig/clock")
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({"TIMEZONE": cfg["timezone"]}, dict(n_cfg))

        contents = util.load_text_file("/etc/localtime")
        self.assertEqual(dummy_contents, contents.strip())
