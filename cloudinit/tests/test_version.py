# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.tests.helpers import CiTestCase
from cloudinit import version

import mock


class TestExportsFeatures(CiTestCase):
    def test_has_network_config_v1(self):
        self.assertIn('NETWORK_CONFIG_V1', version.FEATURES)

    def test_has_network_config_v2(self):
        self.assertIn('NETWORK_CONFIG_V2', version.FEATURES)


class TestVersionString(CiTestCase):
    @mock.patch("cloudinit.version._PACKAGED_VERSION",
                "17.2-3-gb05b9972-0ubuntu1")
    def test_package_version_respected(self):
        """If _PACKAGED_VERSION is filled in, then it should be returned."""
        self.assertEqual("17.2-3-gb05b9972-0ubuntu1", version.version_string())

    @mock.patch("cloudinit.version._PACKAGED_VERSION", "@@PACKAGED_VERSION@@")
    @mock.patch("cloudinit.version.__VERSION__", "17.2")
    def test_package_version_skipped(self):
        """If _PACKAGED_VERSION is not modified, then return __VERSION__."""
        self.assertEqual("17.2", version.version_string())


# vi: ts=4 expandtab
