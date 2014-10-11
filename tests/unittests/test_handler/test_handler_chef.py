import os
import json

from cloudinit.config import cc_chef

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util
from cloudinit.sources import DataSourceNone

from .. import helpers as t_help

import logging

LOG = logging.getLogger(__name__)


class TestChef(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestChef, self).setUp()
        self.tmp = self.makeDir(prefix="unittest_")

    def fetch_cloud(self, distro_kind):
        cls = distros.fetch(distro_kind)
        paths = helpers.Paths({})
        distro = cls(distro_kind, {}, paths)
        ds = DataSourceNone.DataSourceNone({}, distro, paths, None)
        return cloud.Cloud(ds, paths, {}, distro, None)

    def test_no_config(self):
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        cfg = {}
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        for d in cc_chef.CHEF_DIRS:
            self.assertFalse(os.path.isdir(d))

    def test_basic_config(self):
        tpl_file = util.load_file('templates/chef_client.rb.tmpl')
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        util.write_file('/etc/cloud/templates/chef_client.rb.tmpl', tpl_file)
        cfg = {
            'chef': {
                'server_url': 'localhost',
                'validation_name': 'bob',
            },
        }
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        for d in cc_chef.CHEF_DIRS:
            self.assertTrue(os.path.isdir(d))
        c = util.load_file(cc_chef.CHEF_RB_PATH)
        for k, v in cfg['chef'].items():
            self.assertIn(v, c)
        for k, v in cc_chef.CHEF_RB_TPL_DEFAULTS.items():
            if isinstance(v, basestring):
                self.assertIn(v, c)
        c = util.load_file(cc_chef.CHEF_FB_PATH)
        self.assertEqual({}, json.loads(c))

    def test_firstboot_json(self):
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        cfg = {
            'chef': {
                'server_url': 'localhost',
                'validation_name': 'bob',
                'run_list': ['a', 'b', 'c'],
                'initial_attributes': {
                    'c': 'd',
                }
            },
        }
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        c = util.load_file(cc_chef.CHEF_FB_PATH)
        self.assertEqual(
            {
                'run_list': ['a', 'b', 'c'],
                'c': 'd',
            }, json.loads(c))
