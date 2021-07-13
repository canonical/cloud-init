# This file is part of cloud-init. See LICENSE file for license information.

from . import _get_distro
from cloudinit import util
from cloudinit.tests.helpers import mock
from cloudinit.tests.helpers import CiTestCase

SYSTEM_INFO = {
    'paths': {
        'cloud_dir': '/var/lib/cloud/',
        'templates_dir': '/etc/cloud/templates/',
    },
    'network': {'renderers': 'networkd'},
}


class TestPhoton(CiTestCase):
    with_logs = True
    distro = _get_distro('photon', SYSTEM_INFO)
    expected_log_line = 'Rely on PhotonOS default network config'

    def test_network_renderer(self):
        self.assertEqual(self.distro._cfg['network']['renderers'], 'networkd')

    def test_get_distro(self):
        self.assertEqual(self.distro.osfamily, 'photon')

    def test_write_hostname(self):
        hostname = 'myhostname'
        hostfile = self.tmp_path('hostfile')
        self.distro._write_hostname(hostname, hostfile)
        self.assertEqual(hostname + '\n', util.load_file(hostfile))

    @mock.patch('cloudinit.net.generate_fallback_config')
    def test_fallback_netcfg(self, m_fallback_cfg):

        key = 'disable_fallback_netcfg'
        # Don't use fallback if no setting given
        self.logs.truncate(0)
        assert(self.distro.generate_fallback_config() is None)
        self.assertIn(self.expected_log_line, self.logs.getvalue())

        self.logs.truncate(0)
        self.distro._cfg[key] = True
        assert(self.distro.generate_fallback_config() is None)
        self.assertIn(self.expected_log_line, self.logs.getvalue())

        self.logs.truncate(0)
        self.distro._cfg[key] = False
        assert(self.distro.generate_fallback_config() is not None)
        self.assertNotIn(self.expected_log_line, self.logs.getvalue())
