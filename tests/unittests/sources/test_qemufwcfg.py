# This file is part of cloud-init. See LICENSE file for license information.

import logging

import pytest
import yaml

import cloudinit.sources.DataSourceQemuFwCfg as ds_mod
from cloudinit.sources.DataSourceQemuFwCfg import (
    DEFAULT_IID,
    DataSourceQemuFwCfg,
)


@pytest.fixture
def fwcfg_path(tmp_path, mocker):
    """Redirect FWCFG_PATH to a temporary directory and return it."""
    mocker.patch.object(ds_mod, "FWCFG_PATH", str(tmp_path))
    return tmp_path


def write_slot(fwcfg_path, name: str, content: bytes) -> None:
    """Write content into the ``<name>/raw`` file under fwcfg_path."""
    slot_dir = fwcfg_path / name
    slot_dir.mkdir(parents=True, exist_ok=True)
    (slot_dir / "raw").write_bytes(content)


@pytest.fixture
def ds(paths):
    return DataSourceQemuFwCfg(sys_cfg={}, distro=None, paths=paths)


class TestDsDetect:
    def test_true_when_path_exists(self, fwcfg_path, ds):
        assert ds.ds_detect() is True

    def test_false_when_path_absent(self, tmp_path, ds, mocker):
        mocker.patch.object(
            ds_mod, "FWCFG_PATH", str(tmp_path / "nonexistent")
        )
        assert ds.ds_detect() is False


class TestGetDataRequired:
    def test_both_required_slots_present(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: my-id\n")
        write_slot(fwcfg_path, "user-data", b"#cloud-config\n{}")
        assert ds.get_data() is True

    def test_missing_meta_data_returns_false(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "user-data", b"#cloud-config\n{}")
        assert ds.get_data() is False

    def test_missing_user_data_returns_false(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: my-id\n")
        assert ds.get_data() is False

    def test_no_slots_returns_false(self, fwcfg_path, ds):
        assert ds.get_data() is False


class TestGetDataMetadata:
    def test_instance_id_from_meta_data(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: my-vm\n")
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.metadata["instance-id"] == "my-vm"

    def test_get_instance_id(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: test-id-123\n")
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.get_instance_id() == "test-id-123"

    def test_default_instance_id_when_absent_from_meta_data(
        self, fwcfg_path, ds
    ):
        write_slot(fwcfg_path, "meta-data", b"local-hostname: myhost\n")
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.metadata["instance-id"] == DEFAULT_IID

    def test_invalid_yaml_meta_data_logs_warning_and_uses_default(
        self, fwcfg_path, ds, caplog
    ):
        # YAML list is not a dict: load_yaml returns None, slot still 'found'
        write_slot(fwcfg_path, "meta-data", b"- item1\n- item2\n")
        write_slot(fwcfg_path, "user-data", b"")
        with caplog.at_level(logging.WARNING):
            result = ds.get_data()
        assert result is True
        assert "did not parse as a YAML dict" in caplog.text
        assert ds.metadata["instance-id"] == DEFAULT_IID

    def test_extra_metadata_keys_preserved(self, fwcfg_path, ds):
        md = {"instance-id": "i-1", "local-hostname": "myhost"}
        write_slot(fwcfg_path, "meta-data", yaml.dump(md).encode())
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.metadata["local-hostname"] == "myhost"


class TestGetDataPayloads:
    def test_user_data_stored(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"#cloud-config\npackages: [git]")
        ds.get_data()
        assert ds.userdata_raw == "#cloud-config\npackages: [git]"

    def test_invalid_utf8_bytes_replaced(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"#cloud-config\n\xff\xfe")
        ds.get_data()
        assert "�" in ds.userdata_raw

    def test_vendor_data_stored(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        write_slot(fwcfg_path, "vendor-data", b"#cloud-config\nruncmd: [true]")
        ds.get_data()
        assert ds.vendordata_raw == "#cloud-config\nruncmd: [true]"

    def test_vendor_data_empty_string_when_slot_absent(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.vendordata_raw == ""


class TestGetDataNetworkConfig:
    def test_network_config_parsed(self, fwcfg_path, ds):
        netconf = {"version": 2, "ethernets": {"eth0": {"dhcp4": True}}}
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        write_slot(fwcfg_path, "network-config", yaml.dump(netconf).encode())
        ds.get_data()
        assert ds.network_config == netconf

    def test_network_config_none_when_slot_absent(self, fwcfg_path, ds):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        ds.get_data()
        assert ds.network_config is None

    def test_network_config_invalid_yaml_treated_as_absent(
        self, fwcfg_path, ds
    ):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        write_slot(fwcfg_path, "network-config", b"invalid: [unclosed")
        ds.get_data()
        assert ds.network_config is None


class TestGetDataErrors:
    def test_oserror_on_slot_logs_warning_and_continues(
        self, fwcfg_path, ds, caplog
    ):
        write_slot(fwcfg_path, "meta-data", b"instance-id: i-1\n")
        write_slot(fwcfg_path, "user-data", b"")
        # raw as a directory triggers IsADirectoryError (OSError) on open()
        (fwcfg_path / "vendor-data" / "raw").mkdir(parents=True)
        with caplog.at_level(logging.WARNING):
            assert ds.get_data() is True
        assert "vendor-data" in caplog.text


class TestDataSourceMetadata:
    def test_subplatform_format(self, ds):
        assert ds.subplatform == "fw_cfg (%s)" % ds_mod.FWCFG_PATH

    def test_cloud_name_is_unknown(self, ds):
        assert ds.cloud_name == "unknown"
