# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import shutil
import tempfile
from io import BytesIO
from unittest import mock

from configobj import ConfigObj

from cloudinit import cloud, distros, helpers, util
from cloudinit.config import cc_set_hostname
from tests.unittests import helpers as t_help

LOG = logging.getLogger(__name__)


class TestHostname(t_help.FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestHostname, self).setUp()
        self.tmp = tempfile.mkdtemp()
        util.ensure_dir(os.path.join(self.tmp, "data"))
        self.addCleanup(shutil.rmtree, self.tmp)

    def _fetch_distro(self, kind, conf=None):
        cls = distros.fetch(kind)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        conf = {} if conf is None else conf
        return cls(kind, conf, paths)

    def test_debian_write_hostname_prefer_fqdn(self):
        cfg = {
            "hostname": "blah",
            "prefer_fqdn_over_hostname": True,
            "fqdn": "blah.yahoo.com",
        }
        distro = self._fetch_distro("debian", cfg)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, LOG, [])
        contents = util.load_file("/etc/hostname")
        self.assertEqual("blah.yahoo.com", contents.strip())

    @mock.patch("cloudinit.distros.Distro.uses_systemd", return_value=False)
    def test_rhel_write_hostname_prefer_hostname(self, m_uses_systemd):
        cfg = {
            "hostname": "blah",
            "prefer_fqdn_over_hostname": False,
            "fqdn": "blah.yahoo.com",
        }
        distro = self._fetch_distro("rhel", cfg)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, LOG, [])
        contents = util.load_file("/etc/sysconfig/network", decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({"HOSTNAME": "blah"}, dict(n_cfg))

    @mock.patch("cloudinit.distros.Distro.uses_systemd", return_value=False)
    def test_write_hostname_rhel(self, m_uses_systemd):
        cfg = {"hostname": "blah", "fqdn": "blah.blah.blah.yahoo.com"}
        distro = self._fetch_distro("rhel")
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, LOG, [])
        contents = util.load_file("/etc/sysconfig/network", decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({"HOSTNAME": "blah.blah.blah.yahoo.com"}, dict(n_cfg))

    def test_write_hostname_debian(self):
        cfg = {
            "hostname": "blah",
            "fqdn": "blah.blah.blah.yahoo.com",
        }
        distro = self._fetch_distro("debian")
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, LOG, [])
        contents = util.load_file("/etc/hostname")
        self.assertEqual("blah", contents.strip())

    @mock.patch("cloudinit.distros.Distro.uses_systemd", return_value=False)
    def test_write_hostname_sles(self, m_uses_systemd):
        cfg = {
            "hostname": "blah.blah.blah.suse.com",
        }
        distro = self._fetch_distro("sles")
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, LOG, [])
        contents = util.load_file(distro.hostname_conf_fn)
        self.assertEqual("blah", contents.strip())

    @mock.patch("cloudinit.distros.photon.subp.subp")
    def test_photon_hostname(self, m_subp):
        cfg1 = {
            "hostname": "photon",
            "prefer_fqdn_over_hostname": True,
            "fqdn": "test1.vmware.com",
        }
        cfg2 = {
            "hostname": "photon",
            "prefer_fqdn_over_hostname": False,
            "fqdn": "test2.vmware.com",
        }

        ds = None
        m_subp.return_value = (None, None)
        distro = self._fetch_distro("photon", cfg1)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        for c in [cfg1, cfg2]:
            cc_set_hostname.handle("cc_set_hostname", c, cc, LOG, [])
            print("\n", m_subp.call_args_list)
            if c["prefer_fqdn_over_hostname"]:
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["fqdn"]],
                        capture=True,
                    )
                ] in m_subp.call_args_list
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["hostname"]],
                        capture=True,
                    )
                ] not in m_subp.call_args_list
            else:
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["hostname"]],
                        capture=True,
                    )
                ] in m_subp.call_args_list
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["fqdn"]],
                        capture=True,
                    )
                ] not in m_subp.call_args_list

    def test_multiple_calls_skips_unchanged_hostname(self):
        """Only new hostname or fqdn values will generate a hostname call."""
        distro = self._fetch_distro("debian")
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname1.me.com"}, cc, LOG, []
        )
        contents = util.load_file("/etc/hostname")
        self.assertEqual("hostname1", contents.strip())
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname1.me.com"}, cc, LOG, []
        )
        self.assertIn(
            "DEBUG: No hostname changes. Skipping set-hostname\n",
            self.logs.getvalue(),
        )
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname2.me.com"}, cc, LOG, []
        )
        contents = util.load_file("/etc/hostname")
        self.assertEqual("hostname2", contents.strip())
        self.assertIn(
            "Non-persistently setting the system hostname to hostname2",
            self.logs.getvalue(),
        )

    def test_error_on_distro_set_hostname_errors(self):
        """Raise SetHostnameError on exceptions from distro.set_hostname."""
        distro = self._fetch_distro("debian")

        def set_hostname_error(hostname, fqdn):
            raise Exception("OOPS on: %s" % fqdn)

        distro.set_hostname = set_hostname_error
        paths = helpers.Paths({"cloud_dir": self.tmp})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        with self.assertRaises(cc_set_hostname.SetHostnameError) as ctx_mgr:
            cc_set_hostname.handle(
                "somename", {"hostname": "hostname1.me.com"}, cc, LOG, []
            )
        self.assertEqual(
            "Failed to set the hostname to hostname1.me.com (hostname1):"
            " OOPS on: hostname1.me.com",
            str(ctx_mgr.exception),
        )


# vi: ts=4 expandtab
