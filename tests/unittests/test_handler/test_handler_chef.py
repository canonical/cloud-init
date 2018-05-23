# This file is part of cloud-init. See LICENSE file for license information.

import httpretty
import json
import logging
import os
import six

from cloudinit import cloud
from cloudinit.config import cc_chef
from cloudinit import distros
from cloudinit import helpers
from cloudinit.sources import DataSourceNone
from cloudinit import util

from cloudinit.tests.helpers import (
    HttprettyTestCase, FilesystemMockingTestCase, mock, skipIf)

LOG = logging.getLogger(__name__)

CLIENT_TEMPL = os.path.sep.join(["templates", "chef_client.rb.tmpl"])

# This is adjusted to use http because using with https causes issue
# in some openssl/httpretty combinations.
#   https://github.com/gabrielfalcao/HTTPretty/issues/242
# We saw issue in opensuse 42.3 with
#    httpretty=0.8.8-7.1 ndg-httpsclient=0.4.0-3.2 pyOpenSSL=16.0.0-4.1
OMNIBUS_URL_HTTP = cc_chef.OMNIBUS_URL.replace("https:", "http:")


class TestInstallChefOmnibus(HttprettyTestCase):

    def setUp(self):
        super(TestInstallChefOmnibus, self).setUp()
        self.new_root = self.tmp_dir()

    @mock.patch("cloudinit.config.cc_chef.OMNIBUS_URL", OMNIBUS_URL_HTTP)
    def test_install_chef_from_omnibus_runs_chef_url_content(self):
        """install_chef_from_omnibus runs downloaded OMNIBUS_URL as script."""
        chef_outfile = self.tmp_path('chef.out', self.new_root)
        response = '#!/bin/bash\necho "Hi Mom" > {0}'.format(chef_outfile)
        httpretty.register_uri(
            httpretty.GET, cc_chef.OMNIBUS_URL, body=response, status=200)
        cc_chef.install_chef_from_omnibus()
        self.assertEqual('Hi Mom\n', util.load_file(chef_outfile))

    @mock.patch('cloudinit.config.cc_chef.url_helper.readurl')
    @mock.patch('cloudinit.config.cc_chef.util.subp_blob_in_tempfile')
    def test_install_chef_from_omnibus_retries_url(self, m_subp_blob, m_rdurl):
        """install_chef_from_omnibus retries OMNIBUS_URL upon failure."""

        class FakeURLResponse(object):
            contents = '#!/bin/bash\necho "Hi Mom" > {0}/chef.out'.format(
                self.new_root)

        m_rdurl.return_value = FakeURLResponse()

        cc_chef.install_chef_from_omnibus()
        expected_kwargs = {'retries': cc_chef.OMNIBUS_URL_RETRIES,
                           'url': cc_chef.OMNIBUS_URL}
        self.assertItemsEqual(expected_kwargs, m_rdurl.call_args_list[0][1])
        cc_chef.install_chef_from_omnibus(retries=10)
        expected_kwargs = {'retries': 10,
                           'url': cc_chef.OMNIBUS_URL}
        self.assertItemsEqual(expected_kwargs, m_rdurl.call_args_list[1][1])
        expected_subp_kwargs = {
            'args': ['-v', '2.0'],
            'basename': 'chef-omnibus-install',
            'blob': m_rdurl.return_value.contents,
            'capture': False
        }
        self.assertItemsEqual(
            expected_subp_kwargs,
            m_subp_blob.call_args_list[0][1])

    @mock.patch("cloudinit.config.cc_chef.OMNIBUS_URL", OMNIBUS_URL_HTTP)
    @mock.patch('cloudinit.config.cc_chef.util.subp_blob_in_tempfile')
    def test_install_chef_from_omnibus_has_omnibus_version(self, m_subp_blob):
        """install_chef_from_omnibus provides version arg to OMNIBUS_URL."""
        chef_outfile = self.tmp_path('chef.out', self.new_root)
        response = '#!/bin/bash\necho "Hi Mom" > {0}'.format(chef_outfile)
        httpretty.register_uri(
            httpretty.GET, cc_chef.OMNIBUS_URL, body=response)
        cc_chef.install_chef_from_omnibus(omnibus_version='2.0')

        called_kwargs = m_subp_blob.call_args_list[0][1]
        expected_kwargs = {
            'args': ['-v', '2.0'],
            'basename': 'chef-omnibus-install',
            'blob': response,
            'capture': False
        }
        self.assertItemsEqual(expected_kwargs, called_kwargs)


class TestChef(FilesystemMockingTestCase):

    def setUp(self):
        super(TestChef, self).setUp()
        self.tmp = self.tmp_dir()

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

    @skipIf(not os.path.isfile(CLIENT_TEMPL),
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

    @skipIf(not os.path.isfile(CLIENT_TEMPL),
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

    @skipIf(not os.path.isfile(CLIENT_TEMPL),
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
