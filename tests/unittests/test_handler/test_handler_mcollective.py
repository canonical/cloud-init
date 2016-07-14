from cloudinit.config import cc_mcollective
from cloudinit import util

from .. import helpers

import configobj
import logging
import shutil
from six import BytesIO
import tempfile

LOG = logging.getLogger(__name__)


class TestConfig(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

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
        self.patchUtils(self.tmp)
        cc_mcollective.configure(cfg['mcollective']['conf'])
        contents = util.load_file("/etc/mcollective/server.cfg", decode=False)
        contents = configobj.ConfigObj(BytesIO(contents))
        expected = {
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
        }
        self.assertEqual(expected, dict(contents))
