# This file is part of cloud-init. See LICENSE file for license information.

from copy import copy
from unittest import mock

import pytest
import yaml

from cloudinit import helpers, settings, url_helper
from cloudinit.sources import DataSourceMAAS
from tests.unittests.helpers import populate_dir


class TestMAASDataSource:
    def test_seed_dir_valid(self, tmpdir):
        """Verify a valid seeddir is read as such."""

        userdata = b"valid01-userdata"
        data = {
            "meta-data/instance-id": "i-valid01",
            "meta-data/local-hostname": "valid01-hostname",
            "user-data": userdata,
            "public-keys": "ssh-rsa AAAAB3Nz...aC1yc2E= keyname",
        }

        my_d = tmpdir.join("valid").strpath
        populate_dir(my_d, data)

        ud, md, vd = DataSourceMAAS.read_maas_seed_dir(my_d)

        assert userdata == ud
        for key in ("instance-id", "local-hostname"):
            assert data["meta-data/" + key] == md[key]

        # verify that 'userdata' is not returned as part of the metadata
        assert "user-data" not in md
        assert vd is None

    def test_seed_dir_valid_extra(self, tmpdir):
        """Verify extra files do not affect seed_dir validity."""

        userdata = b"valid-extra-userdata"
        data = {
            "meta-data/instance-id": "i-valid-extra",
            "meta-data/local-hostname": "valid-extra-hostname",
            "user-data": userdata,
            "foo": "bar",
        }

        my_d = tmpdir.join("valid_extra").strpath
        populate_dir(my_d, data)

        ud, md, _vd = DataSourceMAAS.read_maas_seed_dir(my_d)

        assert userdata == ud
        for key in ("instance-id", "local-hostname"):
            assert data["meta-data/" + key] == md[key]

        # additional files should not just appear as keys in metadata atm
        assert "foo" not in md

    def test_seed_dir_invalid(self, tmpdir):
        """Verify that invalid seed_dir raises MAASSeedDirMalformed."""

        valid = {
            "instance-id": "i-instanceid",
            "local-hostname": "test-hostname",
            "user-data": "",
        }

        my_based = tmpdir.join("valid_extra").strpath

        # missing 'userdata' file
        my_d = "%s-01" % my_based
        invalid_data = copy(valid)
        del invalid_data["local-hostname"]
        populate_dir(my_d, invalid_data)
        with pytest.raises(DataSourceMAAS.MAASSeedDirMalformed):
            DataSourceMAAS.read_maas_seed_dir(my_d)

        # missing 'instance-id'
        my_d = "%s-02" % my_based
        invalid_data = copy(valid)
        del invalid_data["instance-id"]
        populate_dir(my_d, invalid_data)
        with pytest.raises(DataSourceMAAS.MAASSeedDirMalformed):
            DataSourceMAAS.read_maas_seed_dir(my_d)

    def test_seed_dir_none(self, tmpdir):
        """Verify that empty seed_dir raises MAASSeedDirNone."""

        my_d = tmpdir.join("valid_extra").strpath
        with pytest.raises(DataSourceMAAS.MAASSeedDirNone):
            DataSourceMAAS.read_maas_seed_dir(my_d)

    def test_seed_dir_missing(self, tmpdir):
        """Verify that missing seed_dir raises MAASSeedDirNone."""
        with pytest.raises(DataSourceMAAS.MAASSeedDirNone):
            DataSourceMAAS.read_maas_seed_dir(
                tmpdir.join("doesnotexist").strpath
            )

    def mock_read_maas_seed_url(self, data, seed, version="19991231"):
        """mock up readurl to appear as a web server at seed has provided data.
        return what read_maas_seed_url returns."""

        def my_readurl(*args, **kwargs):
            if len(args):
                url = args[0]
            else:
                url = kwargs["url"]
            prefix = "%s/%s/" % (seed, version)
            if not url.startswith(prefix):
                raise ValueError("unexpected call %s" % url)

            short = url[len(prefix) :]
            if short not in data:
                raise url_helper.UrlError("not found", code=404, url=url)
            return url_helper.StringResponse(data[short])

        # Now do the actual call of the code under test.
        with mock.patch("cloudinit.url_helper.readurl") as mock_readurl:
            mock_readurl.side_effect = my_readurl
            return DataSourceMAAS.read_maas_seed_url(seed, version=version)

    def test_seed_url_valid(self, tmpdir):
        """Verify that valid seed_url is read as such."""
        valid = {
            "meta-data/instance-id": "i-instanceid",
            "meta-data/local-hostname": "test-hostname",
            "meta-data/public-keys": "test-hostname",
            "meta-data/vendor-data": b"my-vendordata",
            "user-data": b"foodata",
        }
        my_seed = "http://example.com/xmeta"
        my_ver = "1999-99-99"
        ud, md, vd = self.mock_read_maas_seed_url(valid, my_seed, my_ver)

        assert valid["meta-data/instance-id"] == md["instance-id"]
        assert valid["meta-data/local-hostname"] == md["local-hostname"]
        assert valid["meta-data/public-keys"] == md["public-keys"]
        assert valid["user-data"] == ud
        # vendor-data is yaml, which decodes a string
        assert valid["meta-data/vendor-data"].decode() == vd

    def test_seed_url_vendor_data_dict(self):
        expected_vd = {"key1": "value1"}
        valid = {
            "meta-data/instance-id": "i-instanceid",
            "meta-data/local-hostname": "test-hostname",
            "meta-data/vendor-data": yaml.safe_dump(expected_vd).encode(),
        }
        _ud, md, vd = self.mock_read_maas_seed_url(
            valid, "http://example.com/foo"
        )

        assert valid["meta-data/instance-id"] == md["instance-id"]
        assert expected_vd == vd

    @pytest.mark.parametrize(
        "initramfs_file, cmdline_value, expected",
        (
            pytest.param(
                None,
                "no net in cmdline",
                False,
                id="no_maas_local_when_missing_run_files_and_cmdline",
            ),
            pytest.param(
                "some initramfs cfg",
                "no net in cmdline",
                False,
                id="no_maas_local_when_run_files_and_no_cmdline",
            ),
            pytest.param(
                "some initframfs cfg",
                "ip=dhcp cmdline config",
                True,
                id="maas_local_when_run_and_ip_cmdline_present",
            ),
        ),
    )
    @pytest.mark.usefixtures("fake_filesystem")
    @mock.patch("cloudinit.util.get_cmdline")
    def tests_wb_local_stage_detects_datasource_on_initramfs_network(
        self, cmdline, initramfs_file, cmdline_value, expected, tmpdir
    ):
        """Only detect local MAAS datasource net config is seen in initframfs

        MAAS Ephemeral launches provide initramfs network configuration to the
        instance being launched. Assert that MAASDataSourceLocal can only be
        discovered and detected when initramfs net config is applicable.

        The datasource needs to also prioritize the network config on disk
        before initramfs configuration. Because the ephemeral instance
        launches provide a custom cloud-config-url that will provide
        network configuration to the VM which is more complete than the
        initramfs config.
        """
        cmdline.return_value = cmdline_value
        ds = DataSourceMAAS.DataSourceMAASLocal(
            settings.CFG_BUILTIN, None, helpers.Paths({"cloud_dir": tmpdir})
        )
        tmpdir.mkdir("run")

        # Create valid maas seed dir so parent DataSourceMAAS.get_data succeeds
        tmpdir.mkdir("seed")
        seed_dir = tmpdir.join("seed/maas")
        seed_dir.mkdir()
        userdata = b"valid01-userdata"
        data = {
            "meta-data/instance-id": "i-valid01",
            "meta-data/local-hostname": "valid01-hostname",
            "user-data": userdata,
            "public-keys": "ssh-rsa AAAAB3Nz...aC1yc2E= keyname",
        }
        populate_dir(seed_dir.strpath, data)

        if initramfs_file:
            klibc_net_cfg = tmpdir.join("run/net-eno.conf")
            klibc_net_cfg.write(initramfs_file)
        assert expected == ds.get_data()


@mock.patch("cloudinit.sources.DataSourceMAAS.url_helper.OauthUrlHelper")
class TestGetOauthHelper:
    base_cfg = {
        "consumer_key": "FAKE_CONSUMER_KEY",
        "token_key": "FAKE_TOKEN_KEY",
        "token_secret": "FAKE_TOKEN_SECRET",
        "consumer_secret": None,
    }

    def test_all_required(self, m_helper):
        """Valid config as expected."""
        DataSourceMAAS.get_oauth_helper(self.base_cfg.copy())
        m_helper.assert_has_calls([mock.call(**self.base_cfg)])

    def test_other_fields_not_passed_through(self, m_helper):
        """Only relevant fields are passed through."""
        mycfg = self.base_cfg.copy()
        mycfg["unrelated_field"] = "unrelated"
        DataSourceMAAS.get_oauth_helper(mycfg)
        m_helper.assert_has_calls([mock.call(**self.base_cfg)])


class TestGetIdHash:
    v1_cfg = {
        "consumer_key": "CKEY",
        "token_key": "TKEY",
        "token_secret": "TSEC",
    }
    v1_id = (
        "v1:403ee5f19c956507f1d0e50814119c405902137ea4f8838bde167c5da8110392"
    )

    def test_v1_expected(self):
        """Test v1 id generated as expected working behavior from config."""
        result = DataSourceMAAS.get_id_from_ds_cfg(self.v1_cfg.copy())
        assert self.v1_id == result

    def test_v1_extra_fields_are_ignored(self):
        """Test v1 id ignores unused entries in config."""
        cfg = self.v1_cfg.copy()
        cfg["consumer_secret"] = "BOO"
        cfg["unrelated"] = "HI MOM"
        result = DataSourceMAAS.get_id_from_ds_cfg(cfg)
        assert self.v1_id == result
