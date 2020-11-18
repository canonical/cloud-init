import os
import re
import json
from cloudinit.sources import DataSourceConfigDrive as dscd
from cloudinit.sources import DataSourceOpenStack as dsos
from cloudinit.sources import DataSourceOVF as dsovf
from cloudinit import helpers
from cloudinit.tests import helpers as tests_helpers
from cloudinit.tests.helpers import mock
from cloudinit import util
from cloudinit.tests.helpers import populate_dir
from cloudinit import stages
from cloudinit import safeyaml
import httpretty as hp
from tests.unittests.test_datasource import test_openstack
from tests.unittests.test_datasource import test_ovf
from tests.unittests.test_datasource import test_configdrive


class FallbackDatasource(tests_helpers.FilesystemMockingTestCase,
                         tests_helpers.HttprettyTestCase):
    VERSION = 'latest'

    def setUp(self):
        super(FallbackDatasource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})

    def simulate_cloudinit_boot(self, dsrc=None):
        self.reRoot(self.tmp)
        initer = stages.Init(ds_deps=['FILESYSTEM'])
        initer.datasource = dsrc
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        iid = initer.instancify()
        initer.update()
        return iid

    def remove_seed_dir(self, seed_dir):
        self.patched_funcs.close()
        util.del_dir(seed_dir)

    def get_sys_cfg(self, dstype, dsmode):
        sys_cfg = {
            'datasource_list': [dstype],
            'datasource': {'ConfigDrive': {'dsmode': dsmode}}
        }
        cloud_cfg = safeyaml.dumps(sys_cfg)
        util.write_file(os.path.join(self.tmp, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        return sys_cfg


class TestConfigDriveFallback(FallbackDatasource):
    def setUp(self):
        super(TestConfigDriveFallback, self).setUp()
        self.ds = dscd.DataSourceConfigDrive
        self.sys_cfg = self.get_sys_cfg('ConfigDrive', 'local')
        self.seed_dir = os.path.join(self.paths.seed_dir, "config_drive")
        populate_dir(self.seed_dir, test_configdrive.CFG_DRIVE_FILES_V2)

    def test_invalid_config_drive(self):
        dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
        self.assertTrue(dsrc.get_data())

        # simulate first boot with config drive
        iid_with_dsrc = self.simulate_cloudinit_boot(dsrc)

        # invalidate config drive to force fallback
        self.remove_seed_dir(self.seed_dir)
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))

        # simulate subsequent boot without config drive
        iid_without_dsrc = self.simulate_cloudinit_boot()
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)


class TestOpenStackFallback(FallbackDatasource):
    def setUp(self):
        super(TestOpenStackFallback, self).setUp()
        self.ds = dsos.DataSourceOpenStack
        self.sys_cfg = self.get_sys_cfg('OpenStack', 'net')
        test_openstack._register_uris(self.VERSION, {}, {},
                                      test_openstack.OS_FILES)

    def test_invalid_openstack_uri(self):
        dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
        MOCK_PATH = 'cloudinit.sources.DataSourceOpenStack.'
        mock_path = MOCK_PATH + 'detect_openstack'
        with tests_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            self.assertTrue(dsrc.get_data())

        # simulate first boot with datasource openstack
        iid_with_dsrc = self.simulate_cloudinit_boot(dsrc=dsrc)

        # invalidate openstack uri to force fallback
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))
        url = re.compile(r'http://169.254.169.254/.*')
        hp.register_uri(hp.GET, url, status=504)

        # simulate subsequent boot without datasource openstack
        iid_without_dsrc = self.simulate_cloudinit_boot()
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)


class TestOVFFallback(FallbackDatasource):
    def setUp(self):
        super(TestOVFFallback, self).setUp()
        self.ds = dsovf.DataSourceOVF
        props = {"password": "passw0rd", "instance-id": "inst-001"}
        env = test_ovf.fill_properties(props)
        ovf_env = self.tmp_path('ovf-env.xml', dir=self.paths.seed_dir)
        util.write_file(ovf_env, env)

    def test_invalid_ovf(self):
        dsrc = self.ds(sys_cfg={}, distro=None, paths=self.paths)
        MPATH = 'cloudinit.sources.DataSourceOVF.'
        with mock.patch(MPATH + 'transport_vmware_guestinfo') as m_guestd:
            with mock.patch(MPATH + 'transport_iso9660') as m_iso9660:
                m_iso9660.return_value = None
                m_guestd.return_value = None
                self.assertTrue(dsrc.get_data())

        # simulate first boot with datasource OVF
        iid_with_dsrc = self.simulate_cloudinit_boot(dsrc=dsrc)

        # invalidated OVF to force fallback
        self.remove_seed_dir(self.paths.seed_dir)
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))

        # simulate subsequent boot without datasource OVF
        iid_without_dsrc = self.simulate_cloudinit_boot()
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)
