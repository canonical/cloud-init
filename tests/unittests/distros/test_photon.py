# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from tests.unittests.distros import _get_distro
from tests.unittests.helpers import CiTestCase, mock

SYSTEM_INFO = {
    "paths": {
        "cloud_dir": "/var/lib/cloud/",
        "templates_dir": "/etc/cloud/templates/",
    },
    "network": {"renderers": "networkd"},
}


class TestPhoton(CiTestCase):
    with_logs = True
    distro = _get_distro("photon", SYSTEM_INFO)
    expected_log_line = "Rely on PhotonOS default network config"

    def test_network_renderer(self):
        self.assertEqual(self.distro._cfg["network"]["renderers"], "networkd")

    def test_get_distro(self):
        self.assertEqual(self.distro.osfamily, "photon")

    @mock.patch("cloudinit.distros.photon.subp.subp")
    def test_write_hostname(self, m_subp):
        hostname = "myhostname"
        hostfile = self.tmp_path("previous-hostname")
        self.distro._write_hostname(hostname, hostfile)
        self.assertEqual(hostname, util.load_text_file(hostfile))

        ret = self.distro._read_hostname(hostfile)
        self.assertEqual(ret, hostname)

        m_subp.return_value = (None, None)
        hostfile += "hostfile"
        self.distro._write_hostname(hostname, hostfile)

        m_subp.return_value = (hostname, None)
        ret = self.distro._read_hostname(hostfile)
        self.assertEqual(ret, hostname)

        self.logs.truncate(0)
        m_subp.return_value = (None, "bla")
        self.distro._write_hostname(hostname, None)
        self.assertIn("Error while setting hostname", self.logs.getvalue())

    @mock.patch("cloudinit.net.generate_fallback_config")
    def test_fallback_netcfg(self, m_fallback_cfg):

        key = "disable_fallback_netcfg"
        # Don't use fallback if no setting given
        self.logs.truncate(0)
        assert self.distro.generate_fallback_config() is None
        self.assertIn(self.expected_log_line, self.logs.getvalue())

        self.logs.truncate(0)
        self.distro._cfg[key] = True
        assert self.distro.generate_fallback_config() is None
        self.assertIn(self.expected_log_line, self.logs.getvalue())

        self.logs.truncate(0)
        self.distro._cfg[key] = False
        assert self.distro.generate_fallback_config() is not None
        self.assertNotIn(self.expected_log_line, self.logs.getvalue())
