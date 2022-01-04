# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import shutil

from cloudinit import cloud, distros, helpers, util
from cloudinit.config import cc_update_etc_hosts
from tests.unittests import helpers as t_help

LOG = logging.getLogger(__name__)


class TestHostsFile(t_help.FilesystemMockingTestCase):
    def setUp(self):
        super(TestHostsFile, self).setUp()
        self.tmp = self.tmp_dir()

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def test_write_etc_hosts_suse_localhost(self):
        cfg = {
            "manage_etc_hosts": "localhost",
            "hostname": "cloud-init.test.us",
        }
        os.makedirs("%s/etc/" % self.tmp)
        hosts_content = "192.168.1.1 blah.blah.us blah\n"
        fout = open("%s/etc/hosts" % self.tmp, "w")
        fout.write(hosts_content)
        fout.close()
        distro = self._fetch_distro("sles")
        distro.hosts_fn = "%s/etc/hosts" % self.tmp
        paths = helpers.Paths({})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_update_etc_hosts.handle("test", cfg, cc, LOG, [])
        contents = util.load_file("%s/etc/hosts" % self.tmp)
        if "127.0.1.1\tcloud-init.test.us\tcloud-init" not in contents:
            self.assertIsNone("No entry for 127.0.1.1 in etc/hosts")
        if "192.168.1.1\tblah.blah.us\tblah" not in contents:
            self.assertIsNone("Default etc/hosts content modified")

    @t_help.skipUnlessJinja()
    def test_write_etc_hosts_suse_template(self):
        cfg = {
            "manage_etc_hosts": "template",
            "hostname": "cloud-init.test.us",
        }
        shutil.copytree(
            t_help.cloud_init_project_dir("templates"),
            "%s/etc/cloud/templates" % self.tmp,
        )
        distro = self._fetch_distro("sles")
        paths = helpers.Paths({})
        paths.template_tpl = "%s" % self.tmp + "/etc/cloud/templates/%s.tmpl"
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        self.patchUtils(self.tmp)
        cc_update_etc_hosts.handle("test", cfg, cc, LOG, [])
        contents = util.load_file("%s/etc/hosts" % self.tmp)
        if "127.0.1.1 cloud-init.test.us cloud-init" not in contents:
            self.assertIsNone("No entry for 127.0.1.1 in etc/hosts")
        if "::1 cloud-init.test.us cloud-init" not in contents:
            self.assertIsNone("No entry for 127.0.0.1 in etc/hosts")
