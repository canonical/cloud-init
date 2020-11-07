# This file is part of cloud-init. See LICENSE file for license information.

import os
import json
from cloudinit.sources import DataSourceConfigDrive as ds
from cloudinit import helpers
from cloudinit.tests import helpers as tests_helpers
from cloudinit import util
from cloudinit.tests.helpers import populate_dir
from cloudinit import stages
from cloudinit import safeyaml


OSTACK_META = {
    'availability_zone': 'nova',
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c'}


CFG_DRIVE_FILES_V2 = {
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META)}


class TestFallbackDatasource(tests_helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestFallbackDatasource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})
        self.ds = ds.DataSourceConfigDrive

    def test_invalid_config_drive(self):
        seed_dir = os.path.join(self.paths.seed_dir, "config_drive")
        populate_dir(seed_dir, CFG_DRIVE_FILES_V2)

        sys_cfg = {
            'datasource': {'ConfigDrive': {'dsmode': 'local'}}
        }

        cloud_cfg = safeyaml.dumps(sys_cfg)
        util.ensure_dir(os.path.join(self.tmp, 'etc', 'cloud'))
        util.write_file(os.path.join(self.tmp, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        dsrc = self.ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(
            dsrc.subplatform, 'seed-dir (%s)' % seed_dir)
        self.assertTrue(ret)
        # simulate first boot with config drive
        self.reRoot(self.tmp)
        initer = stages.Init()
        initer.datasource = dsrc
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        iid_with_dsrc = initer.instancify()
        initer.update()
        # simulate subsequent boot without config drive
        self.patched_funcs.close()
        util.del_dir(seed_dir)
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))
        util.del_file(os.path.join(self.tmp, ".instance-id"))
        self.reRoot(self.tmp)
        initer = stages.Init(ds_deps=['FILESYSTEM'])
        initer.fetch()
        initer.read_cfg()
        initer.initialize()
        iid_without_dsrc = initer.instancify()
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)
        initer.update()
