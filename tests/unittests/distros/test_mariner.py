# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import get_distro

SYSTEM_INFO = {
    "paths": {
        "cloud_dir": "/var/lib/cloud/",
        "templates_dir": "/etc/cloud/templates/",
    },
    "network": {"renderers": "networkd"},
}


class TestMariner:
    distro = get_distro("mariner", SYSTEM_INFO)
    expected_log_line = "Rely on MarinerOS default network config"

    def test_network_renderer(self):
        assert self.distro._cfg["network"]["renderers"] == "networkd"

    def test_get_distro(self):
        assert self.distro.osfamily == "mariner"
