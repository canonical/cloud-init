# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging


from cloudinit import util
from cloudinit.config import cc_timezone
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestTimezone:

    def test_set_timezone_sles(self, fake_filesystem):
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
        n_cfg = {}
        for line in contents.decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                n_cfg[key.strip()] = value.strip()

        assert {"TIMEZONE": cfg["timezone"]} == dict(n_cfg)

        localtime_contents = util.load_text_file("/etc/localtime")
        assert dummy_contents == localtime_contents.strip()
