# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import os
import shutil
import six
import tempfile

from cloudinit import cloud
from cloudinit.config import cc_chef
from cloudinit import distros
from cloudinit import helpers
from cloudinit.sources import DataSourceNone
from cloudinit import util

from .. import helpers as t_help

LOG = logging.getLogger(__name__)

CLIENT_TEMPL = os.path.sep.join(["templates", "chef_client.rb.tmpl"])


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

    @t_help.skipIf(not os.path.isfile(CLIENT_TEMPL),
                   CLIENT_TEMPL + " is not available")
    def test_basic_config(self):
        """
        test basic config looks sane

        # This should create a file of the format...
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
                'validation_key': "/etc/chef/vkey.pem",
                'validation_cert': "this is my cert",
            },
        }
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        for d in cc_chef.CHEF_DIRS:
            self.assertTrue(os.path.isdir(d))
        c = util.load_file(cc_chef.CHEF_RB_PATH)

        # the content of these keys is not expected to be rendered to tmpl
        unrendered_keys = ('validation_cert',)
        for k, v in cfg['chef'].items():
            if k in unrendered_keys:
                continue
            self.assertIn(v, c)
        for k, v in cc_chef.CHEF_RB_TPL_DEFAULTS.items():
            if k in unrendered_keys:
                continue
            # the value from the cfg overrides that in the default
            val = cfg['chef'].get(k, v)
            if isinstance(val, six.string_types):
                self.assertIn(val, c)
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

    @t_help.skipIf(not os.path.isfile(CLIENT_TEMPL),
                   CLIENT_TEMPL + " is not available")
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

    @t_help.skipIf(not os.path.isfile(CLIENT_TEMPL),
                   CLIENT_TEMPL + " is not available")
    def test_validation_cert_and_validation_key(self):
        # test validation_cert content is written to validation_key path
        tpl_file = util.load_file('templates/chef_client.rb.tmpl')
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        util.write_file('/etc/cloud/templates/chef_client.rb.tmpl', tpl_file)
        v_path = '/etc/chef/vkey.pem'
        v_cert = 'this is my cert'
        cfg = {
            'chef': {
                'server_url': 'localhost',
                'validation_name': 'bob',
                'validation_key': v_path,
                'validation_cert': v_cert
            },
        }
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        content = util.load_file(cc_chef.CHEF_RB_PATH)
        self.assertIn(v_path, content)
        util.load_file(v_path)
        self.assertEqual(v_cert, util.load_file(v_path))

    def test_validation_cert_with_system(self):
        # test validation_cert content is not written over system file
        tpl_file = util.load_file('templates/chef_client.rb.tmpl')
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)

        v_path = '/etc/chef/vkey.pem'
        v_cert = "system"
        expected_cert = "this is the system file certificate"
        cfg = {
            'chef': {
                'server_url': 'localhost',
                'validation_name': 'bob',
                'validation_key': v_path,
                'validation_cert': v_cert
            },
        }
        util.write_file('/etc/cloud/templates/chef_client.rb.tmpl', tpl_file)
        util.write_file(v_path, expected_cert)
        cc_chef.handle('chef', cfg, self.fetch_cloud('ubuntu'), LOG, [])
        content = util.load_file(cc_chef.CHEF_RB_PATH)
        self.assertIn(v_path, content)
        util.load_file(v_path)
        self.assertEqual(expected_cert, util.load_file(v_path))

# vi: ts=4 expandtab
