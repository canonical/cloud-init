from cloudinit.config import cc_lxd
from cloudinit import (distros, helpers, cloud)
from cloudinit.sources import DataSourceNoCloud
from .. import helpers as t_help

import logging

try:
    from unittest import mock
except ImportError:
    import mock

LOG = logging.getLogger(__name__)


class TestLxd(t_help.TestCase):
    lxd_cfg = {
        'lxd': {
            'init': {
                'network_address': '0.0.0.0',
                'storage_backend': 'zfs',
                'storage_pool': 'poolname',
            }
        }
    }

    def setUp(self):
        super(TestLxd, self).setUp()

    def _get_cloud(self, distro):
        cls = distros.fetch(distro)
        paths = helpers.Paths({})
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    @mock.patch("cloudinit.config.cc_lxd.util")
    def test_lxd_init(self, mock_util):
        cc = self._get_cloud('ubuntu')
        mock_util.which.return_value = True
        cc_lxd.handle('cc_lxd', self.lxd_cfg, cc, LOG, [])
        self.assertTrue(mock_util.which.called)
        init_call = mock_util.subp.call_args_list[0][0][0]
        self.assertEquals(init_call,
                          ['lxd', 'init', '--auto',
                           '--network-address=0.0.0.0',
                           '--storage-backend=zfs',
                           '--storage-pool=poolname'])

    @mock.patch("cloudinit.config.cc_lxd.util")
    def test_lxd_install(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        mock_util.which.return_value = None
        cc_lxd.handle('cc_lxd', self.lxd_cfg, cc, LOG, [])
        self.assertTrue(cc.distro.install_packages.called)
        install_pkg = cc.distro.install_packages.call_args_list[0][0][0]
        self.assertEquals(sorted(install_pkg), ['lxd', 'zfs'])

    @mock.patch("cloudinit.config.cc_lxd.util")
    def test_no_init_does_nothing(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc_lxd.handle('cc_lxd', {'lxd': {}}, cc, LOG, [])
        self.assertFalse(cc.distro.install_packages.called)
        self.assertFalse(mock_util.subp.called)

    @mock.patch("cloudinit.config.cc_lxd.util")
    def test_no_lxd_does_nothing(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc_lxd.handle('cc_lxd', {'package_update': True}, cc, LOG, [])
        self.assertFalse(cc.distro.install_packages.called)
        self.assertFalse(mock_util.subp.called)
