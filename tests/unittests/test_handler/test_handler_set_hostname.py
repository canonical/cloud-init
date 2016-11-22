# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_set_hostname

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from .. import helpers as t_help

from configobj import ConfigObj
import logging
import shutil
from six import BytesIO
import tempfile

LOG = logging.getLogger(__name__)


class TestHostname(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestHostname, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def test_write_hostname_rhel(self):
        cfg = {
            'hostname': 'blah.blah.blah.yahoo.com',
        }
        distro = self._fetch_distro('rhel')
        paths = helpers.Paths({})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle('cc_set_hostname',
                               cfg, cc, LOG, [])
        if not distro.uses_systemd():
            contents = util.load_file("/etc/sysconfig/network", decode=False)
            n_cfg = ConfigObj(BytesIO(contents))
            self.assertEqual({'HOSTNAME': 'blah.blah.blah.yahoo.com'},
                             dict(n_cfg))

    def test_write_hostname_debian(self):
        cfg = {
            'hostname': 'blah.blah.blah.yahoo.com',
        }
        distro = self._fetch_distro('debian')
        paths = helpers.Paths({})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle('cc_set_hostname',
                               cfg, cc, LOG, [])
        contents = util.load_file("/etc/hostname")
        self.assertEqual('blah', contents.strip())

    def test_write_hostname_sles(self):
        cfg = {
            'hostname': 'blah.blah.blah.suse.com',
        }
        distro = self._fetch_distro('sles')
        paths = helpers.Paths({})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle('cc_set_hostname', cfg, cc, LOG, [])
        contents = util.load_file("/etc/HOSTNAME")
        self.assertEqual('blah', contents.strip())

# vi: ts=4 expandtab
