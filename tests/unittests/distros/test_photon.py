# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from tests.unittests.helpers import get_distro, mock

SYSTEM_INFO = {
    "paths": {
        "cloud_dir": "/var/lib/cloud/",
        "templates_dir": "/etc/cloud/templates/",
    },
    "network": {"renderers": "networkd"},
}


class TestPhoton:
    distro = get_distro("photon", SYSTEM_INFO)
    expected_log_line = "Rely on PhotonOS default network config"

    def test_network_renderer(self):
        assert self.distro._cfg["network"]["renderers"] == "networkd"

    def test_get_distro(self):
        assert self.distro.osfamily == "photon"

    @mock.patch("cloudinit.distros.photon.subp.subp")
    def test_write_hostname(self, m_subp, caplog, tmp_path):
        hostname = "myhostname"
        hostfile = str(tmp_path / "previous-hostname")
        self.distro._write_hostname(hostname, hostfile)
        assert hostname == util.load_text_file(hostfile)

        ret = self.distro._read_hostname(hostfile)
        assert ret == hostname

        m_subp.return_value = (None, None)
        hostfile += "hostfile"
        self.distro._write_hostname(hostname, hostfile)

        m_subp.return_value = (hostname, None)
        ret = self.distro._read_hostname(hostfile)
        assert ret == hostname

        caplog.clear()
        m_subp.return_value = (None, "bla")
        self.distro._write_hostname(hostname, None)
        assert "Error while setting hostname" in caplog.text

    @mock.patch("cloudinit.net.generate_fallback_config")
    def test_fallback_netcfg(self, m_fallback_cfg, caplog):

        key = "disable_fallback_netcfg"
        # Don't use fallback if no setting given
        caplog.clear()
        assert self.distro.generate_fallback_config() is None
        assert self.expected_log_line in caplog.text

        caplog.clear()
        self.distro._cfg[key] = True
        assert self.distro.generate_fallback_config() is None
        assert self.expected_log_line in caplog.text

        caplog.clear()
        self.distro._cfg[key] = False
        assert self.distro.generate_fallback_config() is not None
        assert self.expected_log_line not in caplog.text
