#    Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    Based on test_handler_set_hostname.py
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from cloudinit.config import cc_locale

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNoCloud

from .. import helpers as t_help

from configobj import ConfigObj

from StringIO import StringIO

import logging

LOG = logging.getLogger(__name__)


class TestLocale(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestLocale, self).setUp()
        self.new_root = self.makeDir(prefix="unittest_")

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

        contents = util.load_file('/etc/sysconfig/language')
        n_cfg = ConfigObj(StringIO(contents))
        self.assertEquals({'RC_LANG': cfg['locale']}, dict(n_cfg))
