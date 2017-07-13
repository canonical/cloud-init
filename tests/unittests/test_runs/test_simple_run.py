# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil
import tempfile

from .. import helpers

from cloudinit.settings import PER_INSTANCE
from cloudinit import stages
from cloudinit import util


class TestSimpleRun(helpers.FilesystemMockingTestCase):
    def _patchIn(self, root):
        self.patchOS(root)
        self.patchUtils(root)

    def test_none_ds(self):
        new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, new_root)
        self.replicateTestRoot('simple_ubuntu', new_root)
        cfg = {
            'datasource_list': ['None'],
            'write_files': [
                {
                    'path': '/etc/blah.ini',
                    'content': 'blah',
                    'permissions': 0o755,
                },
            ],
            'cloud_init_modules': ['write-files'],
        }
        cloud_cfg = util.yaml_dumps(cfg)
        util.ensure_dir(os.path.join(new_root, 'etc', 'cloud'))
        util.write_file(os.path.join(new_root, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        self._patchIn(new_root)

        # Now start verifying whats created
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        self.assertTrue(os.path.exists("/var/lib/cloud"))
        for d in ['scripts', 'seed', 'instances', 'handlers', 'sem', 'data']:
            self.assertTrue(os.path.isdir(os.path.join("/var/lib/cloud", d)))

        initer.fetch()
        iid = initer.instancify()
        self.assertEqual(iid, 'iid-datasource-none')
        initer.update()
        self.assertTrue(os.path.islink("var/lib/cloud/instance"))

        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)

        mods = stages.Modules(initer)
        (which_ran, failures) = mods.run_section('cloud_init_modules')
        self.assertTrue(len(failures) == 0)
        self.assertTrue(os.path.exists('/etc/blah.ini'))
        self.assertIn('write-files', which_ran)
        contents = util.load_file('/etc/blah.ini')
        self.assertEqual(contents, 'blah')

# vi: ts=4 expandtab
