# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

from cloudinit import version


class TestExportsFeatures:
    def test_has_network_config_v1(self):
        assert "NETWORK_CONFIG_V1" in version.FEATURES

    def test_has_network_config_v2(self):
        assert "NETWORK_CONFIG_V2" in version.FEATURES


class TestVersionString:
    @mock.patch(
        "cloudinit.version._PACKAGED_VERSION", "17.2-3-gb05b9972-0ubuntu1"
    )
    def test_package_version_respected(self):
        """If _PACKAGED_VERSION is filled in, then it should be returned."""
        assert "17.2-3-gb05b9972-0ubuntu1" == version.version_string()

    @mock.patch("cloudinit.version._PACKAGED_VERSION", "@@PACKAGED_VERSION@@")
    @mock.patch("cloudinit.version.__VERSION__", "17.2")
    def test_package_version_skipped(self):
        """If _PACKAGED_VERSION is not modified, then return __VERSION__."""
        assert "17.2" == version.version_string()
