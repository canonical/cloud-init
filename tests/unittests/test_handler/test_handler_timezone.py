# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_timezone

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNoCloud

from .. import helpers as t_help

from configobj import ConfigObj
import logging
import shutil
from six import BytesIO
import tempfile

LOG = logging.getLogger(__name__)


class TestTimezone(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestTimezone, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro):
        self.patchUtils(self.new_root)
        self.patchOS(self.new_root)

        paths = helpers.Paths({})

        cls = distros.fetch(distro)
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    def test_set_timezone_sles(self):

        cfg = {
            'timezone': 'Tatooine/Bestine',
        }
        cc = self._get_cloud('sles')

        # Create a dummy timezone file
        dummy_contents = '0123456789abcdefgh'
        util.write_file('/usr/share/zoneinfo/%s' % cfg['timezone'],
                        dummy_contents)

        cc_timezone.handle('cc_timezone', cfg, cc, LOG, [])

        contents = util.load_file('/etc/sysconfig/clock', decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({'TIMEZONE': cfg['timezone']}, dict(n_cfg))

        contents = util.load_file('/etc/localtime')
        self.assertEqual(dummy_contents, contents.strip())

# vi: ts=4 expandtab
