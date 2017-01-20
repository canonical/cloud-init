# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit.sources import DataSourceNoCloud
from cloudinit import util
from ..helpers import TestCase, populate_dir, mock, ExitStack

import os
import shutil
import tempfile
import textwrap
import yaml


class TestNoCloudDataSource(TestCase):

    def setUp(self):
        super(TestNoCloudDataSource, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.paths = helpers.Paths({'cloud_dir': self.tmp})

        self.cmdline = "root=TESTCMDLINE"

        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        self.mocks.enter_context(
            mock.patch.object(util, 'get_cmdline', return_value=self.cmdline))

    def test_nocloud_seed_dir(self):
        md = {'instance-id': 'IID', 'dsmode': 'local'}
        ud = b"USER_DATA_HERE"
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

        self.mocks.enter_context(
            mock.patch.object(util, 'find_devs_with',
                              side_effect=PsuedoException))

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
            'meta-data': yaml.safe_dump({'instance-id': 'IID'}),
            'user-data': b"USER_DATA_RAW",
        }

        sys_cfg = {'datasource': {'NoCloud': data}}
        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, b"USER_DATA_RAW")
        self.assertEqual(dsrc.metadata.get('instance-id'), 'IID')
        self.assertTrue(ret)

    def test_nocloud_seed_with_vendordata(self):
        md = {'instance-id': 'IID', 'dsmode': 'local'}
        ud = b"USER_DATA_HERE"
        vd = b"THIS IS MY VENDOR_DATA"

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
        self.assertEqual(dsrc.vendordata_raw, vd)
        self.assertTrue(ret)

    def test_nocloud_no_vendordata(self):
        populate_dir(os.path.join(self.paths.seed_dir, "nocloud"),
                     {'user-data': b"ud", 'meta-data': "instance-id: IID\n"})

        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, b"ud")
        self.assertFalse(dsrc.vendordata)
        self.assertTrue(ret)

    def test_metadata_network_interfaces(self):
        gateway = "103.225.10.1"
        md = {
            'instance-id': 'i-abcd',
            'local-hostname': 'hostname1',
            'network-interfaces': textwrap.dedent("""\
                auto eth0
                iface eth0 inet static
                hwaddr 00:16:3e:70:e1:04
                address 103.225.10.12
                netmask 255.255.255.0
                gateway """ + gateway + """
                dns-servers 8.8.8.8""")}

        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {'user-data': b"ud",
             'meta-data': yaml.dump(md) + "\n"})

        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        # very simple check just for the strings above
        self.assertIn(gateway, str(dsrc.network_config))

    def test_metadata_network_config(self):
        # network-config needs to get into network_config
        netconf = {'version': 1,
                   'config': [{'type': 'physical', 'name': 'interface0',
                               'subnets': [{'type': 'dhcp'}]}]}
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {'user-data': b"ud",
             'meta-data': "instance-id: IID\n",
             'network-config': yaml.dump(netconf) + "\n"})

        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(netconf, dsrc.network_config)

    def test_metadata_network_config_over_interfaces(self):
        # network-config should override meta-data/network-interfaces
        gateway = "103.225.10.1"
        md = {
            'instance-id': 'i-abcd',
            'local-hostname': 'hostname1',
            'network-interfaces': textwrap.dedent("""\
                auto eth0
                iface eth0 inet static
                hwaddr 00:16:3e:70:e1:04
                address 103.225.10.12
                netmask 255.255.255.0
                gateway """ + gateway + """
                dns-servers 8.8.8.8""")}

        netconf = {'version': 1,
                   'config': [{'type': 'physical', 'name': 'interface0',
                               'subnets': [{'type': 'dhcp'}]}]}
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {'user-data': b"ud",
             'meta-data': yaml.dump(md) + "\n",
             'network-config': yaml.dump(netconf) + "\n"})

        sys_cfg = {'datasource': {'NoCloud': {'fs_label': None}}}

        ds = DataSourceNoCloud.DataSourceNoCloud

        dsrc = ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(netconf, dsrc.network_config)
        self.assertNotIn(gateway, str(dsrc.network_config))


class TestParseCommandLineData(TestCase):

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


# vi: ts=4 expandtab
