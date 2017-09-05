# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import (cloud, distros, helpers, util)
from cloudinit.config import cc_mcollective
from cloudinit.sources import DataSourceNoCloud

from cloudinit.tests import helpers as t_help

import configobj
import logging
import os
import shutil
from six import BytesIO
import tempfile

LOG = logging.getLogger(__name__)


STOCK_CONFIG = """\
main_collective = mcollective
collectives = mcollective
libdir = /usr/share/mcollective/plugins
logfile = /var/log/mcollective.log
loglevel = info
daemonize = 1

# Plugins
securityprovider = psk
plugin.psk = unset

connector = activemq
plugin.activemq.pool.size = 1
plugin.activemq.pool.1.host = stomp1
plugin.activemq.pool.1.port = 61613
plugin.activemq.pool.1.user = mcollective
plugin.activemq.pool.1.password = marionette

# Facts
factsource = yaml
plugin.yaml = /etc/mcollective/facts.yaml
"""


class TestConfig(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        # "./": make os.path.join behave correctly with abs path as second arg
        self.server_cfg = os.path.join(
            self.tmp, "./" + cc_mcollective.SERVER_CFG)
        self.pubcert_file = os.path.join(
            self.tmp, "./" + cc_mcollective.PUBCERT_FILE)
        self.pricert_file = os.path.join(
            self.tmp, self.tmp, "./" + cc_mcollective.PRICERT_FILE)

    def test_basic_config(self):
        cfg = {
            'mcollective': {
                'conf': {
                    'loglevel': 'debug',
                    'connector': 'rabbitmq',
                    'logfile': '/var/log/mcollective.log',
                    'ttl': '4294957',
                    'collectives': 'mcollective',
                    'main_collective': 'mcollective',
                    'securityprovider': 'psk',
                    'daemonize': '1',
                    'factsource': 'yaml',
                    'direct_addressing': '1',
                    'plugin.psk': 'unset',
                    'libdir': '/usr/share/mcollective/plugins',
                    'identity': '1',
                },
            },
        }
        expected = cfg['mcollective']['conf']

        self.patchUtils(self.tmp)
        cc_mcollective.configure(cfg['mcollective']['conf'])
        contents = util.load_file(cc_mcollective.SERVER_CFG, decode=False)
        contents = configobj.ConfigObj(BytesIO(contents))
        self.assertEqual(expected, dict(contents))

    def test_existing_config_is_saved(self):
        cfg = {'loglevel': 'warn'}
        util.write_file(self.server_cfg, STOCK_CONFIG)
        cc_mcollective.configure(config=cfg, server_cfg=self.server_cfg)
        self.assertTrue(os.path.exists(self.server_cfg))
        self.assertTrue(os.path.exists(self.server_cfg + ".old"))
        self.assertEqual(util.load_file(self.server_cfg + ".old"),
                         STOCK_CONFIG)

    def test_existing_updated(self):
        cfg = {'loglevel': 'warn'}
        util.write_file(self.server_cfg, STOCK_CONFIG)
        cc_mcollective.configure(config=cfg, server_cfg=self.server_cfg)
        cfgobj = configobj.ConfigObj(self.server_cfg)
        self.assertEqual(cfg['loglevel'], cfgobj['loglevel'])

    def test_certificats_written(self):
        # check public-cert and private-cert keys in config get written
        cfg = {'loglevel': 'debug',
               'public-cert': "this is my public-certificate",
               'private-cert': "secret private certificate"}

        cc_mcollective.configure(
            config=cfg, server_cfg=self.server_cfg,
            pricert_file=self.pricert_file, pubcert_file=self.pubcert_file)

        found = configobj.ConfigObj(self.server_cfg)

        # make sure these didnt get written in
        self.assertFalse('public-cert' in found)
        self.assertFalse('private-cert' in found)

        # these need updating to the specified paths
        self.assertEqual(found['plugin.ssl_server_public'], self.pubcert_file)
        self.assertEqual(found['plugin.ssl_server_private'], self.pricert_file)

        # and the security provider should be ssl
        self.assertEqual(found['securityprovider'], 'ssl')

        self.assertEqual(
            util.load_file(self.pricert_file), cfg['private-cert'])
        self.assertEqual(
            util.load_file(self.pubcert_file), cfg['public-cert'])


class TestHandler(t_help.TestCase):
    def _get_cloud(self, distro):
        cls = distros.fetch(distro)
        paths = helpers.Paths({})
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    @t_help.mock.patch("cloudinit.config.cc_mcollective.util")
    def test_mcollective_install(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = t_help.mock.MagicMock()
        mock_util.load_file.return_value = b""
        mycfg = {'mcollective': {'conf': {'loglevel': 'debug'}}}
        cc_mcollective.handle('cc_mcollective', mycfg, cc, LOG, [])
        self.assertTrue(cc.distro.install_packages.called)
        install_pkg = cc.distro.install_packages.call_args_list[0][0][0]
        self.assertEqual(install_pkg, ('mcollective',))

        self.assertTrue(mock_util.subp.called)
        self.assertEqual(mock_util.subp.call_args_list[0][0][0],
                         ['service', 'mcollective', 'restart'])

# vi: ts=4 expandtab
