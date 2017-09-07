# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.tests.helpers import CiTestCase
from cloudinit import version


class TestExportsFeatures(CiTestCase):
    def test_has_network_config_v1(self):
        self.assertIn('NETWORK_CONFIG_V1', version.FEATURES)

    def test_has_network_config_v2(self):
        self.assertIn('NETWORK_CONFIG_V2', version.FEATURES)

# vi: ts=4 expandtab
