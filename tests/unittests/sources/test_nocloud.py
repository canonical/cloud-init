# This file is part of cloud-init. See LICENSE file for license information.

import os
import textwrap

import pytest
import yaml

from cloudinit.sources.DataSourceNoCloud import DataSourceNoCloud as dsNoCloud
from cloudinit.sources.DataSourceNoCloud import (
    DataSourceNoCloudNet,
    parse_cmdline_data,
)
from tests.unittests.helpers import mock, populate_dir


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch("cloudinit.sources.DataSourceNoCloud.util.is_lxd")
    mocker.patch("cloudinit.util.get_cmdline", return_value="root=TESTCMDLINE")
    mocker.patch("cloudinit.dmi.read_dmi_data", return_value=None)


class TestNoCloudDataSource:
    def _test_fs_config_is_read(
        self, fs_label, fs_label_to_search, mocker, paths
    ):
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

        mocker.patch(
            "cloudinit.util.find_devs_with", side_effect=m_find_devs_with
        )
        mocker.patch("cloudinit.util.mount_cb", side_effect=m_mount_cb)
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": fs_label_to_search}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()

        assert dsrc.metadata.get("instance-id") == "IID"
        assert ret

    def test_nocloud_seed_dir_on_lxd(self, paths):
        md = {"instance-id": "IID", "dsmode": "local"}
        ud = b"USER_DATA_HERE"
        seed_dir = os.path.join(paths.seed_dir, "nocloud")
        populate_dir(
            seed_dir, {"user-data": ud, "meta-data": yaml.safe_dump(md)}
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert dsrc.userdata_raw == ud
        assert dsrc.metadata == md
        assert dsrc.platform_type == "lxd"
        assert dsrc.subplatform == "seed-dir (%s)" % seed_dir
        assert ret

    def test_nocloud_seed_dir_non_lxd_platform_is_nocloud(self, mocker, paths):
        """Non-lxd environments will list nocloud as the platform."""
        mocker.patch(
            "cloudinit.sources.DataSourceNoCloud.util.is_lxd",
            return_value=False,
        )
        md = {"instance-id": "IID", "dsmode": "local"}
        seed_dir = os.path.join(paths.seed_dir, "nocloud")
        populate_dir(
            seed_dir, {"user-data": "", "meta-data": yaml.safe_dump(md)}
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        assert dsrc.get_data()
        assert dsrc.platform_type == "nocloud"
        assert dsrc.subplatform == "seed-dir (%s)" % seed_dir

    def test_nocloud_seedfrom(self, paths, caplog):
        """Check that a seedfrom triggers detection"""
        ds = DataSourceNoCloudNet(
            sys_cfg={"datasource": {"NoCloud": {"seedfrom": "somevalue"}}},
            distro=None,
            paths=paths,
        )
        assert ds.ds_detect()
        assert (
            "Machine is configured by system configuration to run on "
            "single datasource DataSourceNoCloudNet"
        ) in caplog.text

    def test_nocloud_user_data_meta_data(self, paths):
        """Check that meta-data and user-data trigger detection"""
        assert dsNoCloud(
            sys_cfg={
                "datasource": {
                    "NoCloud": {
                        "meta-data": "",
                        "user-data": "#cloud-config\nsome-config",
                    }
                }
            },
            distro=None,
            paths=paths,
        ).ds_detect()

    def test_fs_label(self, paths, mocker):
        # find_devs_with should not be called ff fs_label is None
        class PsuedoException(Exception):
            pass

        mocker.patch(
            "cloudinit.util.find_devs_with", side_effect=PsuedoException
        )

        # by default, NoCloud should search for filesystems by label
        sys_cfg = {"datasource": {"NoCloud": {}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        pytest.raises(PsuedoException, dsrc.get_data)

        # but disabling searching should just end up with None found
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert not ret

    def test_fs_config_lowercase_label(self, mocker, paths):
        self._test_fs_config_is_read("cidata", "cidata", mocker, paths)

    def test_fs_config_uppercase_label(self, mocker, paths):
        self._test_fs_config_is_read("CIDATA", "cidata", mocker, paths)

    def test_fs_config_lowercase_label_search_uppercase(self, mocker, paths):
        self._test_fs_config_is_read("cidata", "CIDATA", mocker, paths)

    def test_fs_config_uppercase_label_search_uppercase(self, mocker, paths):
        self._test_fs_config_is_read("CIDATA", "CIDATA", mocker, paths)

    def test_no_datasource_expected(self, paths):
        # no source should be found if no cmdline, config, and fs_label=None
        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        assert not dsrc.get_data()

    def test_seed_in_config(self, paths):
        data = {
            "fs_label": None,
            "meta-data": yaml.safe_dump({"instance-id": "IID"}),
            "user-data": b"USER_DATA_RAW",
        }

        sys_cfg = {"datasource": {"NoCloud": data}}
        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert dsrc.userdata_raw == b"USER_DATA_RAW"
        assert dsrc.metadata.get("instance-id") == "IID"
        assert ret

    def test_nocloud_seed_with_vendordata(self, paths):
        md = {"instance-id": "IID", "dsmode": "local"}
        ud = b"USER_DATA_HERE"
        vd = b"THIS IS MY VENDOR_DATA"

        populate_dir(
            os.path.join(paths.seed_dir, "nocloud"),
            {
                "user-data": ud,
                "meta-data": yaml.safe_dump(md),
                "vendor-data": vd,
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert dsrc.userdata_raw == ud
        assert dsrc.metadata == md
        assert dsrc.vendordata_raw == vd
        assert ret

    def test_nocloud_no_vendordata(self, paths):
        populate_dir(
            os.path.join(paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": "instance-id: IID\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert dsrc.userdata_raw == b"ud"
        assert not dsrc.vendordata
        assert ret

    def test_metadata_network_interfaces(self, paths):
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
            os.path.join(paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": yaml.dump(md) + "\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert ret
        # very simple check just for the strings above
        assert gateway in str(dsrc.network_config)

    def test_metadata_network_config(self, paths):
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
            os.path.join(paths.seed_dir, "nocloud"),
            {
                "user-data": b"ud",
                "meta-data": "instance-id: IID\n",
                "network-config": yaml.dump(netconf) + "\n",
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert ret
        assert netconf == dsrc.network_config

    def test_metadata_network_config_over_interfaces(self, paths):
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
            os.path.join(paths.seed_dir, "nocloud"),
            {
                "user-data": b"ud",
                "meta-data": yaml.dump(md) + "\n",
                "network-config": yaml.dump(netconf) + "\n",
            },
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc.get_data()
        assert ret
        assert netconf == dsrc.network_config
        assert gateway not in str(dsrc.network_config)

    @mock.patch("cloudinit.util.blkid")
    def test_nocloud_get_devices_freebsd(self, fake_blkid, mocker, paths):
        populate_dir(
            os.path.join(paths.seed_dir, "nocloud"),
            {"user-data": b"ud", "meta-data": "instance-id: IID\n"},
        )

        sys_cfg = {"datasource": {"NoCloud": {"fs_label": None}}}

        mocker.patch("cloudinit.util.is_FreeBSD", return_value=True)

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

        mocker.patch(
            "cloudinit.util.find_devs_with",
            side_effect=_mfind_devs_with_freebsd,
        )

        dsrc = dsNoCloud(sys_cfg=sys_cfg, distro=None, paths=paths)
        ret = dsrc._get_devices("foo")
        assert ["/dev/msdosfs/foo", "/dev/iso9660/foo"] == ret
        fake_blkid.assert_not_called()


class TestParseCommandLineData:
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

        for fmt, expected in pairs:
            fill = {}
            cmdline = fmt % {"ds_id": ds_id}
            ret = parse_cmdline_data(ds_id=ds_id, fill=fill, cmdline=cmdline)
            assert expected == fill
            assert ret

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
            assert fill == {}
            assert not ret
