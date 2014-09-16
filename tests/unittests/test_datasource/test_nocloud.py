from cloudinit import helpers
from cloudinit.sources import DataSourceNoCloud
from cloudinit import util
from ..helpers import populate_dir

from mocker import MockerTestCase
import os
import yaml


class TestNoCloudDataSource(MockerTestCase):

    def setUp(self):
        self.tmp = self.makeDir()
        self.paths = helpers.Paths({'cloud_dir': self.tmp})

        self.cmdline = "root=TESTCMDLINE"

        self.unapply = []
        self.apply_patches([(util, 'get_cmdline', self._getcmdline)])
        super(TestNoCloudDataSource, self).setUp()

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])
        super(TestNoCloudDataSource, self).tearDown()

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

    def _getcmdline(self):
        return self.cmdline

    def test_nocloud_seed_dir(self):
        md = {'instance-id': 'IID', 'dsmode': 'local'}
        ud = "USER_DATA_HERE"
        populate_dir(os.path.join(self.paths.seed_dir, "nocloud"),
                     {'user-data': ud, 'meta-data': yaml.safe_dump(md)})

        sys_cfg = {
            'datasource': {'NoCloud': {'fs_label': None}}
        }

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, ud)
        self.assertEqual(dsrc.metadata, md)
        self.assertTrue(ret)

    def test_fs_label(self):
        # find_devs_with should not be called ff fs_label is None
        ds = DataSourceNoCloud.DataSourceNoCloud

        class PsuedoException(Exception):
            pass

        def my_find_devs_with(*args, **kwargs):
            raise PsuedoException

        self.apply_patches([(util, 'find_devs_with', my_find_devs_with)])

        # by default, NoCloud should search for filesystems by label
        sys_cfg = {'datasource': {'NoCloud': {}}}
        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        self.assertRaises(PsuedoException, dsrc.get_data)

        # but disabling searching should just end up with None found
        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}
        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertFalse(ret)

    def test_no_datasource_expected(self):
        # no source should be found if no cmdline, config, and fs_label=None
        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud
        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        self.assertFalse(dsrc.get_data())

    def test_seed_in_config(self):
        ds = DataSourceNoCloud.DataSourceNoCloud

        data = {
            'fs_label': None,
            'meta-data': {'instance-id': 'IID'},
            'user-data': "USER_DATA_RAW",
        }

        sys_cfg = {'datasource': {'NoCloud': data}}
        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, "USER_DATA_RAW")
        self.assertEqual(dsrc.metadata.get('instance-id'), 'IID')
        self.assertTrue(ret)

    def test_nocloud_seed_with_vendordata(self):
        md = {'instance-id': 'IID', 'dsmode': 'local'}
        ud = "USER_DATA_HERE"
        vd = "THIS IS MY VENDOR_DATA"

        populate_dir(os.path.join(self.paths.seed_dir, "nocloud"),
                     {'user-data': ud, 'meta-data': yaml.safe_dump(md),
                      'vendor-data': vd})

        sys_cfg = {
            'datasource': {'NoCloud': {'fs_label': None}}
        }

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, ud)
        self.assertEqual(dsrc.metadata, md)
        self.assertEqual(dsrc.vendordata, vd)
        self.assertTrue(ret)

    def test_nocloud_no_vendordata(self):
        populate_dir(os.path.join(self.paths.seed_dir, "nocloud"),
                     {'user-data': "ud", 'meta-data': "instance-id: IID\n"})

        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, "ud")
        self.assertFalse(dsrc.vendordata)
        self.assertTrue(ret)


class TestParseCommandLineData(MockerTestCase):

    def test_parse_cmdline_data_valid(self):
        ds_id = "ds=nocloud"
        pairs = (
            ("root=/dev/sda1 %(ds_id)s", {}),
            ("%(ds_id)s; root=/dev/foo", {}),
            ("%(ds_id)s", {}),
            ("%(ds_id)s;", {}),
            ("%(ds_id)s;s=SEED", {'seedfrom': 'SEED'}),
            ("%(ds_id)s;seedfrom=SEED;local-hostname=xhost",
             {'seedfrom': 'SEED', 'local-hostname': 'xhost'}),
            ("%(ds_id)s;h=xhost",
             {'local-hostname': 'xhost'}),
            ("%(ds_id)s;h=xhost;i=IID",
             {'local-hostname': 'xhost', 'instance-id': 'IID'}),
        )

        for (fmt, expected) in pairs:
            fill = {}
            cmdline = fmt % {'ds_id': ds_id}
            ret = DataSourceNoCloud.parse_cmdline_data(ds_id=ds_id, fill=fill,
                                                       cmdline=cmdline)
            self.assertEqual(expected, fill)
            self.assertTrue(ret)

    def test_parse_cmdline_data_none(self):
        ds_id = "ds=foo"
        cmdlines = (
            "root=/dev/sda1 ro",
            "console=/dev/ttyS0 root=/dev/foo",
            "",
            "ds=foocloud",
            "ds=foo-net",
            "ds=nocloud;s=SEED",
        )

        for cmdline in cmdlines:
            fill = {}
            ret = DataSourceNoCloud.parse_cmdline_data(ds_id=ds_id, fill=fill,
                                                       cmdline=cmdline)
            self.assertEqual(fill, {})
            self.assertFalse(ret)


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret


# vi: ts=4 expandtab
