# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from pathlib import PurePath

from cloudinit import util
from cloudinit.sources import DataSourceWSL as wsl
from tests.unittests.helpers import CiTestCase, mock

INSTANCE_NAME = "Noble-MLKit"


class TestWSLHelperFunctions(CiTestCase):
    @mock.patch("cloudinit.util.subp.subp")
    def test_instance_name(self, m_subp):
        m_subp.return_value = util.subp.SubpResult(
            "//wsl.localhost/%s/" % (INSTANCE_NAME), ""
        )

        inst = wsl.instance_name()

        self.assertEqual(INSTANCE_NAME, inst)

