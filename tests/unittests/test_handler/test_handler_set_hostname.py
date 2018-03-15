# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_set_hostname

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.tests import helpers as t_help

from configobj import ConfigObj
import logging
import os
import shutil
from six import BytesIO
import tempfile

LOG = logging.getLogger(__name__)


class TestHostname(t_help.FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestHostname, self).setUp()
        self.tmp = tempfile.mkdtemp()
        util.ensure_dir(os.path.join(self.tmp, 'data'))
        self.addCleanup(shutil.rmtree, self.tmp)

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({'cloud_dir': self.tmp})
        return cls(kind, {}, paths)

    def test_write_hostname_rhel(self):
        cfg = {
            'hostname': 'blah.blah.blah.yahoo.com',
        }
        distro = self._fetch_distro('rhel')
        paths = helpers.Paths({'cloud_dir': self.tmp})
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
        paths = helpers.Paths({'cloud_dir': self.tmp})
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
        paths = helpers.Paths({'cloud_dir': self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle('cc_set_hostname', cfg, cc, LOG, [])
        if not distro.uses_systemd():
            contents = util.load_file(distro.hostname_conf_fn)
            self.assertEqual('blah', contents.strip())

    def test_multiple_calls_skips_unchanged_hostname(self):
        """Only new hostname or fqdn values will generate a hostname call."""
        distro = self._fetch_distro('debian')
        paths = helpers.Paths({'cloud_dir': self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle(
            'cc_set_hostname', {'hostname': 'hostname1.me.com'}, cc, LOG, [])
        contents = util.load_file("/etc/hostname")
        self.assertEqual('hostname1', contents.strip())
        cc_set_hostname.handle(
            'cc_set_hostname', {'hostname': 'hostname1.me.com'}, cc, LOG, [])
        self.assertIn(
            'DEBUG: No hostname changes. Skipping set-hostname\n',
            self.logs.getvalue())
        cc_set_hostname.handle(
            'cc_set_hostname', {'hostname': 'hostname2.me.com'}, cc, LOG, [])
        contents = util.load_file("/etc/hostname")
        self.assertEqual('hostname2', contents.strip())
        self.assertIn(
            'Non-persistently setting the system hostname to hostname2',
            self.logs.getvalue())

    def test_error_on_distro_set_hostname_errors(self):
        """Raise SetHostnameError on exceptions from distro.set_hostname."""
        distro = self._fetch_distro('debian')

        def set_hostname_error(hostname, fqdn):
            raise Exception("OOPS on: %s" % fqdn)

        distro.set_hostname = set_hostname_error
        paths = helpers.Paths({'cloud_dir': self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        with self.assertRaises(cc_set_hostname.SetHostnameError) as ctx_mgr:
            cc_set_hostname.handle(
                'somename', {'hostname': 'hostname1.me.com'}, cc, LOG, [])
        self.assertEqual(
            'Failed to set the hostname to hostname1.me.com (hostname1):'
            ' OOPS on: hostname1.me.com',
            str(ctx_mgr.exception))

# vi: ts=4 expandtab
