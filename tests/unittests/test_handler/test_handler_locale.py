# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_locale

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNoCloud

from .. import helpers as t_help

from configobj import ConfigObj

from six import BytesIO

import logging
import shutil
import tempfile

LOG = logging.getLogger(__name__)


class TestLocale(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestLocale, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})

        cls = distros.fetch(distro)
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    def test_set_locale_sles(self):

        cfg = {
            'locale': 'My.Locale',
        }
        cc = self._get_cloud('sles')
        cc_locale.handle('cc_locale', cfg, cc, LOG, [])

        contents = util.load_file('/etc/sysconfig/language', decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({'RC_LANG': cfg['locale']}, dict(n_cfg))

# vi: ts=4 expandtab
