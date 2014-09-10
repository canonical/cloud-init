import os

from .. import helpers

from cloudinit.settings import (PER_INSTANCE)
from cloudinit import stages
from cloudinit import util


class TestMergeRun(helpers.FilesystemMockingTestCase):
    def _patchIn(self, root):
        self.restore()
        self.patchOS(root)
        self.patchUtils(root)

    def test_none_ds(self):
        new_root = self.makeDir()
        self.replicateTestRoot('simple_ubuntu', new_root)
        cfg = {
            'datasource_list': ['None'],
            'cloud_init_modules': ['write-files'],
        }
        ud = self.readResource('user_data.1.txt')
        cloud_cfg = util.yaml_dumps(cfg)
        util.ensure_dir(os.path.join(new_root, 'etc', 'cloud'))
        util.write_file(os.path.join(new_root, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        self._patchIn(new_root)

        # Now start verifying whats created
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.datasource.userdata_raw = ud
        initer.instancify()
        initer.update()
        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)
        mirrors = initer.distro.get_option('package_mirrors')
        self.assertEquals(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEquals(mirror['arches'], ['i386', 'amd64', 'blah'])
        mods = stages.Modules(initer)
        (which_ran, failures) = mods.run_section('cloud_init_modules')
        self.assertTrue(len(failures) == 0)
        self.assertTrue(os.path.exists('/etc/blah.ini'))
        self.assertIn('write-files', which_ran)
        contents = util.load_file('/etc/blah.ini')
        self.assertEquals(contents, 'blah')
