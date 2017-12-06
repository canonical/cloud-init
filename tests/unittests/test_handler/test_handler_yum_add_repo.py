# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_yum_add_repo
from cloudinit import util

from cloudinit.tests import helpers

import logging
import shutil
from six import StringIO
import tempfile

LOG = logging.getLogger(__name__)


class TestConfig(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_bad_config(self):
        cfg = {
            'yum_repos': {
                'epel-testing': {
                    'name': 'Extra Packages for Enterprise Linux 5 - Testing',
                    # Missing this should cause the repo not to be written
                    # 'baseurl': 'http://blah.org/pub/epel/testing/5/$barch',
                    'enabled': False,
                    'gpgcheck': True,
                    'gpgkey': 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL',
                    'failovermethod': 'priority',
                },
            },
        }
        self.patchUtils(self.tmp)
        cc_yum_add_repo.handle('yum_add_repo', cfg, None, LOG, [])
        self.assertRaises(IOError, util.load_file,
                          "/etc/yum.repos.d/epel_testing.repo")

    def test_write_config(self):
        cfg = {
            'yum_repos': {
                'epel-testing': {
                    'name': 'Extra Packages for Enterprise Linux 5 - Testing',
                    'baseurl': 'http://blah.org/pub/epel/testing/5/$basearch',
                    'enabled': False,
                    'gpgcheck': True,
                    'gpgkey': 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL',
                    'failovermethod': 'priority',
                },
            },
        }
        self.patchUtils(self.tmp)
        cc_yum_add_repo.handle('yum_add_repo', cfg, None, LOG, [])
        contents = util.load_file("/etc/yum.repos.d/epel_testing.repo")
        parser = self.parse_and_read(StringIO(contents))
        expected = {
            'epel_testing': {
                'name': 'Extra Packages for Enterprise Linux 5 - Testing',
                'failovermethod': 'priority',
                'gpgkey': 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL',
                'enabled': '0',
                'baseurl': 'http://blah.org/pub/epel/testing/5/$basearch',
                'gpgcheck': '1',
            }
        }
        for section in expected:
            self.assertTrue(parser.has_section(section),
                            "Contains section {0}".format(section))
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)

    def test_write_config_array(self):
        cfg = {
            'yum_repos': {
                'puppetlabs-products': {
                    'name': 'Puppet Labs Products El 6 - $basearch',
                    'baseurl':
                        'http://yum.puppetlabs.com/el/6/products/$basearch',
                    'gpgkey': [
                        'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppetlabs',
                        'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppet',
                    ],
                    'enabled': True,
                    'gpgcheck': True,
                }
            }
        }
        self.patchUtils(self.tmp)
        cc_yum_add_repo.handle('yum_add_repo', cfg, None, LOG, [])
        contents = util.load_file("/etc/yum.repos.d/puppetlabs_products.repo")
        parser = self.parse_and_read(StringIO(contents))
        expected = {
            'puppetlabs_products': {
                'name': 'Puppet Labs Products El 6 - $basearch',
                'baseurl': 'http://yum.puppetlabs.com/el/6/products/$basearch',
                'gpgkey': 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppetlabs\n'
                          'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppet',
                'enabled': '1',
                'gpgcheck': '1',
            }
        }
        for section in expected:
            self.assertTrue(parser.has_section(section),
                            "Contains section {0}".format(section))
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)

# vi: ts=4 expandtab
