# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_yum_add_repo
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
        contents = util.load_file("/etc/yum.repos.d/epel_testing.repo",
                                  decode=False)
        contents = configobj.ConfigObj(BytesIO(contents))
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
        self.assertEqual(expected, dict(contents))

# vi: ts=4 expandtab
