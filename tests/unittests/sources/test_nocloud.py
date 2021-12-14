# This file is part of cloud-init. See LICENSE file for license information.

import os
import textwrap

import yaml

from cloudinit import dmi, helpers, util
from cloudinit.sources.DataSourceNoCloud import DataSourceNoCloud as dsNoCloud
from cloudinit.sources.DataSourceNoCloud import (
    _maybe_remove_top_network,
    parse_cmdline_data,
)
from tests.unittests.helpers import CiTestCase, ExitStack, mock, populate_dir


@mock.patch("cloudinit.sources.DataSourceNoCloud.util.is_lxd")
class TestNoCloudDataSource(CiTestCase):
    def setUp(self):
        super(TestNoCloudDataSource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {"cloud_dir": self.tmp, "run_dir": self.tmp}
        )

        self.cmdline = "root=TESTCMDLINE"

        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        self.mocks.enter_context(
            mock.patch.object(util, "get_cmdline", return_value=self.cmdline)
        )
        self.mocks.enter_context(
            mock.patch.object(dmi, "read_dmi_data", return_value=None)
        )

    def _test_fs_config_is_read(self, fs_label, fs_label_to_search):
        vfat_device = "device-1"

        def m_mount_cb(device, callback, mtype):
            if device == vfat_device:
                return {"meta-data": yaml.dump({"instance-id": "IID"})}
            else:
                return {}

        def m_find_devs_with(query="", path=""):
            if "TYPE=vfat" == query:
                return [vfat_device]
            elif "LABEL={}".format(fs_label) == query:
                return [vfat_device]
            else:
                return []

        self.mocks.enter_context(
            mock.patch.object(
                util, "find_devs_with", side_effect=m_find_devs_with
            )
        )
        self.mocks.enter_context(
            mock.patch.object(util, "mount_cb", side_effect=m_mount_cb)
        )
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": fs_label_to_search}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()

        self.assertEqual(dsrc.metadata.get("instance-id"), "IID")
        self.assertTrue(ret)

    def test_nocloud_seed_dir_on_lxd(self, m_is_lxd):
        md = {"instance-id": "IID", "dsmode": "local"}
        ud = b"USER_DATA_HERE"
        seed_dir = os.path.join(self.paths.seed_dir, "nocloud")
        populate_dir(
            seed_dir, {"user-data": ud, "meta-data": yaml.safe_dump(md)}
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, ud)
        self.assertEqual(dsrc.metadata, md)
        self.assertEqual(dsrc.platform_type, "lxd")
        self.assertEqual(dsrc.subplatform, "seed-dir (%s)" % seed_dir)
        self.assertTrue(ret)

    def test_nocloud_seed_dir_non_lxd_platform_is_nocloud(self, m_is_lxd):
        """Non-lxd environments will list nocloud as the platform."""
        m_is_lxd.return_value = False
        md = {"instance-id": "IID", "dsmode": "local"}
        seed_dir = os.path.join(self.paths.seed_dir, "nocloud")
        populate_dir(
            seed_dir, {"user-data": "", "meta-data": yaml.safe_dump(md)}
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        self.assertTrue(dsrc.get_data())
        self.assertEqual(dsrc.platform_type, "nocloud")
        self.assertEqual(dsrc.subplatform, "seed-dir (%s)" % seed_dir)

    def test_fs_label(self, m_is_lxd):
        # find_devs_with should not be called ff fs_label is None
        class PsuedoException(Exception):
            pass

        self.mocks.enter_context(
            mock.patch.object(
                util, "find_devs_with", side_effect=PsuedoException
            )
        )

        # by default, NoCloud should search for filesystems by label
        sys_cfg = {"datasource": {"NoCloud": {}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        self.assertRaises(PsuedoException, dsrc.get_data)

        # but disabling searching should just end up with None found
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertFalse(ret)

    def test_fs_config_lowercase_label(self, m_is_lxd):
        self._test_fs_config_is_read("cidata", "cidata")

    def test_fs_config_uppercase_label(self, m_is_lxd):
        self._test_fs_config_is_read("CIDATA", "cidata")

    def test_fs_config_lowercase_label_search_uppercase(self, m_is_lxd):
        self._test_fs_config_is_read("cidata", "CIDATA")

    def test_fs_config_uppercase_label_search_uppercase(self, m_is_lxd):
        self._test_fs_config_is_read("CIDATA", "CIDATA")

    def test_no_datasource_expected(self, m_is_lxd):
        # no source should be found if no cmdline, config, and fs_label=None
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        self.assertFalse(dsrc.get_data())

    def test_seed_in_config(self, m_is_lxd):
        data = {
            "fs_label": None,
            "meta-data": yaml.safe_dump({"instance-id": "IID"}),
            "user-data": b"USER_DATA_RAW",
        }

        sys_cfg = {"datasource": {"NoCloud": data}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, b"USER_DATA_RAW")
        self.assertEqual(dsrc.metadata.get("instance-id"), "IID")
        self.assertTrue(ret)

    def test_nocloud_seed_with_vendordata(self, m_is_lxd):
        md = {"instance-id": "IID", "dsmode": "local"}
        ud = b"USER_DATA_HERE"
        vd = b"THIS IS MY VENDOR_DATA"

        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {
                "user-data": ud,
                "meta-data": yaml.safe_dump(md),
                "vendor-data": vd,
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, ud)
        self.assertEqual(dsrc.metadata, md)
        self.assertEqual(dsrc.vendordata_raw, vd)
        self.assertTrue(ret)

    def test_nocloud_no_vendordata(self, m_is_lxd):
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": "instance-id: IID\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(dsrc.userdata_raw, b"ud")
        self.assertFalse(dsrc.vendordata)
        self.assertTrue(ret)

    def test_metadata_network_interfaces(self, m_is_lxd):
        gateway = "103.225.10.1"
        md = {
            "instance-id": "i-abcd",
            "local-hostname": "hostname1",
            "network-interfaces": textwrap.dedent(
                """\
                auto eth0
                iface eth0 inet static
                hwaddr 00:16:3e:70:e1:04
                address 103.225.10.12
                netmask 255.255.255.0
                gateway """
                + gateway
                + """
                dns-servers 8.8.8.8"""
            ),
        }

        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": yaml.dump(md) + "\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        # very simple check just for the strings above
        self.assertIn(gateway, str(dsrc.network_config))

    def test_metadata_network_config(self, m_is_lxd):
        # network-config needs to get into network_config
        netconf = {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": "interface0",
                    "subnets": [{"type": "dhcp"}],
                }
            ],
        }
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {
                "user-data": b"ud",
                "meta-data": "instance-id: IID\n",
                "network-config": yaml.dump(netconf) + "\n",
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(netconf, dsrc.network_config)

    def test_metadata_network_config_with_toplevel_network(self, m_is_lxd):
        """network-config may have 'network' top level key."""
        netconf = {"config": "disabled"}
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {
                "user-data": b"ud",
                "meta-data": "instance-id: IID\n",
                "network-config": yaml.dump({"network": netconf}) + "\n",
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(netconf, dsrc.network_config)

    def test_metadata_network_config_over_interfaces(self, m_is_lxd):
        # network-config should override meta-data/network-interfaces
        gateway = "103.225.10.1"
        md = {
            "instance-id": "i-abcd",
            "local-hostname": "hostname1",
            "network-interfaces": textwrap.dedent(
                """\
                auto eth0
                iface eth0 inet static
                hwaddr 00:16:3e:70:e1:04
                address 103.225.10.12
                netmask 255.255.255.0
                gateway """
                + gateway
                + """
                dns-servers 8.8.8.8"""
            ),
        }

        netconf = {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": "interface0",
                    "subnets": [{"type": "dhcp"}],
                }
            ],
        }
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {
                "user-data": b"ud",
                "meta-data": yaml.dump(md) + "\n",
                "network-config": yaml.dump(netconf) + "\n",
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(netconf, dsrc.network_config)
        self.assertNotIn(gateway, str(dsrc.network_config))

    @mock.patch("cloudinit.util.blkid")
    def test_nocloud_get_devices_freebsd(self, m_is_lxd, fake_blkid):
        populate_dir(
            os.path.join(self.paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": "instance-id: IID\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        self.mocks.enter_context(
            mock.patch.object(util, "is_FreeBSD", return_value=True)
        )

        def _mfind_devs_with_freebsd(
            criteria=None,
            oformat="device",
            tag=None,
            no_cache=False,
            path=None,
        ):
            if not criteria:
                return ["/dev/msdosfs/foo", "/dev/iso9660/foo"]
            if criteria.startswith("LABEL="):
                return ["/dev/msdosfs/foo", "/dev/iso9660/foo"]
            elif criteria == "TYPE=vfat":
                return ["/dev/msdosfs/foo"]
            elif criteria == "TYPE=iso9660":
                return ["/dev/iso9660/foo"]
            return []

        self.mocks.enter_context(
            mock.patch.object(
                util,
                "find_devs_with_freebsd",
                side_effect=_mfind_devs_with_freebsd,
            )
        )

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc._get_devices("foo")
        self.assertEqual(["/dev/msdosfs/foo", "/dev/iso9660/foo"], ret)
        fake_blkid.assert_not_called()


class TestParseCommandLineData(CiTestCase):
    def test_parse_cmdline_data_valid(self):
        ds_id = "ds=nocloud"
        pairs = (
            ("root=/dev/sda1 %(ds_id)s", {}),
            ("%(ds_id)s; root=/dev/foo", {}),
            ("%(ds_id)s", {}),
            ("%(ds_id)s;", {}),
            ("%(ds_id)s;s=SEED", {"seedfrom": "SEED"}),
            (
                "%(ds_id)s;seedfrom=SEED;local-hostname=xhost",
                {"seedfrom": "SEED", "local-hostname": "xhost"},
            ),
            ("%(ds_id)s;h=xhost", {"local-hostname": "xhost"}),
            (
                "%(ds_id)s;h=xhost;i=IID",
                {"local-hostname": "xhost", "instance-id": "IID"},
            ),
        )

        for (fmt, expected) in pairs:
            fill = {}
            cmdline = fmt % {"ds_id": ds_id}
            ret = parse_cmdline_data(ds_id=ds_id, fill=fill, cmdline=cmdline)
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
            ret = parse_cmdline_data(ds_id=ds_id, fill=fill, cmdline=cmdline)
            self.assertEqual(fill, {})
            self.assertFalse(ret)


class TestMaybeRemoveToplevelNetwork(CiTestCase):
    """test _maybe_remove_top_network function."""

    basecfg = [
        {
            "type": "physical",
            "name": "interface0",
            "subnets": [{"type": "dhcp"}],
        }
    ]

    def test_should_remove_safely(self):
        mcfg = {"config": self.basecfg, "version": 1}
        self.assertEqual(mcfg, _maybe_remove_top_network({"network": mcfg}))

    def test_no_remove_if_other_keys(self):
        """should not shift if other keys at top level."""
        mcfg = {
            "network": {"config": self.basecfg, "version": 1},
            "unknown_keyname": "keyval",
        }
        self.assertEqual(mcfg, _maybe_remove_top_network(mcfg))

    def test_no_remove_if_non_dict(self):
        """should not shift if not a dict."""
        mcfg = {"network": '"content here'}
        self.assertEqual(mcfg, _maybe_remove_top_network(mcfg))

    def test_no_remove_if_missing_config_or_version(self):
        """should not shift unless network entry has config and version."""
        mcfg = {"network": {"config": self.basecfg}}
        self.assertEqual(mcfg, _maybe_remove_top_network(mcfg))

        mcfg = {"network": {"version": 1}}
        self.assertEqual(mcfg, _maybe_remove_top_network(mcfg))

    def test_remove_with_config_disabled(self):
        """network/config=disabled should be shifted."""
        mcfg = {"config": "disabled"}
        self.assertEqual(mcfg, _maybe_remove_top_network({"network": mcfg}))


# vi: ts=4 expandtab
