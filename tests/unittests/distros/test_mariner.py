# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import CiTestCase

from . import _get_distro

SYSTEM_INFO = {
    "paths": {
        "cloud_dir": "/var/lib/cloud/",
        "templates_dir": "/etc/cloud/templates/",
    },
    "network": {"renderers": "networkd"},
}


class TestMariner(CiTestCase):
    with_logs = True
    distro = _get_distro("mariner", SYSTEM_INFO)
    expected_log_line = "Rely on MarinerOS default network config"

    def test_network_renderer(self):
        self.assertEqual(self.distro._cfg["network"]["renderers"], "networkd")

    def test_get_distro(self):
        self.assertEqual(self.distro.osfamily, "mariner")
