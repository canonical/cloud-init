from cloudinit.config import cc_lxd
from cloudinit import (util, distros, helpers, cloud)
from cloudinit.sources import DataSourceNoCloud
from .. import helpers as t_help

import logging

LOG = logging.getLogger(__name__)


class TestLxd(t_help.TestCase):
    def setUp(self):
        super(TestLxd, self).setUp()
        self.unapply = []
        apply_patches([(util, 'subp', self._mock_subp)])
        self.subp_called = []

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])

    def _mock_subp(self, *args, **kwargs):
        if 'args' not in kwargs:
            kwargs['args'] = args[0]
        self.subp_called.append(kwargs)
        return

    def _get_cloud(self, distro):
        cls = distros.fetch(distro)
        paths = helpers.Paths({})
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    def test_lxd_init(self):
        cfg = {
            'lxd': {
                'init': {
                    'network_address': '0.0.0.0',
                    'storage_backend': 'zfs',
                    'storage_pool': 'poolname',
                }
            }
        }
        cc = self._get_cloud('ubuntu')
        cc_lxd.handle('cc_lxd', cfg, cc, LOG, [])

        self.assertEqual(
                self.subp_called[0].get('args'),
                ['lxd', 'init', '--auto', '--network-address', '0.0.0.0',
                 '--storage-backend', 'zfs', '--storage-pool', 'poolname'])


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret
