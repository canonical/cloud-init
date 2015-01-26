import json
import os

from cloudinit.config import cc_chef

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util
from cloudinit.sources import DataSourceNone

from .. import helpers as t_help

import six
import logging
import shutil
import tempfile

LOG = logging.getLogger(__name__)


class TestChef(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestChef, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

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
        # This should create a file of the format...
        """
        # Created by cloud-init v. 0.7.6 on Sat, 11 Oct 2014 23:57:21 +0000
        log_level              :info
        ssl_verify_mode        :verify_none
        log_location           "/var/log/chef/client.log"
        validation_client_name "bob"
        validation_key         "/etc/chef/validation.pem"
        client_key             "/etc/chef/client.pem"
        chef_server_url        "localhost"
        environment            "_default"
        node_name              "iid-datasource-none"
        json_attribs           "/etc/chef/firstboot.json"
        file_cache_path        "/var/cache/chef"
        file_backup_path       "/var/backups/chef"
        pid_file               "/var/run/chef/client.pid"
        Chef::Log::Formatter.show_time = true
        """
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
            if isinstance(v, six.string_types):
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

    def test_template_deletes(self):
        tpl_file = util.load_file('templates/chef_client.rb.tmpl')
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        util.write_file('/etc/cloud/templates/chef_client.rb.tmpl', tpl_file)
        cfg = {
            'chef': {
                'server_url': 'localhost',
                'validation_name': 'bob',
                'json_attribs': None,
                'show_time': None,
            },
        }
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        c = util.load_file(cc_chef.CHEF_RB_PATH)
        self.assertNotIn('json_attribs', c)
        self.assertNotIn('Formatter.show_time', c)
