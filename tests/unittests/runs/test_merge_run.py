# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil
import tempfile

from cloudinit import safeyaml, stages, util
from cloudinit.config.modules import Modules
from cloudinit.settings import PER_INSTANCE
from tests.unittests import helpers


class TestMergeRun(helpers.FilesystemMockingTestCase):
    def _patchIn(self, root):
        self.patchOS(root)
        self.patchUtils(root)

    def test_none_ds(self):
        new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, new_root)
        self.replicateTestRoot("simple_ubuntu", new_root)
        cfg = {
            "datasource_list": ["None"],
            "cloud_init_modules": ["write_files"],
            "system_info": {"paths": {"run_dir": new_root}},
        }
        ud = helpers.readResource("user_data.1.txt")
        cloud_cfg = safeyaml.dumps(cfg)
        util.ensure_dir(os.path.join(new_root, "etc", "cloud"))
        util.write_file(
            os.path.join(new_root, "etc", "cloud", "cloud.cfg"), cloud_cfg
        )
        self._patchIn(new_root)

        # Now start verifying whats created
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.datasource.userdata_raw = ud
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mirrors = initer.distro.get_option("package_mirrors")
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual(mirror["arches"], ["i386", "amd64", "blah"])
        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        self.assertTrue(len(failures) == 0)
        self.assertTrue(os.path.exists("/etc/blah.ini"))
        self.assertIn("write_files", which_ran)
        contents = util.load_text_file("/etc/blah.ini")
        self.assertEqual(contents, "blah")
