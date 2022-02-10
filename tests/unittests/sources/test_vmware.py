# Copyright (c) 2021 VMware, Inc. All Rights Reserved.
#
# Authors: Andrew Kutz <akutz@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import os

import pytest

from cloudinit import dmi, helpers, safeyaml, settings
from cloudinit.sources import DataSourceVMware
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    populate_dir,
)

PRODUCT_NAME_FILE_PATH = "/sys/class/dmi/id/product_name"
PRODUCT_NAME = "VMware7,1"
PRODUCT_UUID = "82343CED-E4C7-423B-8F6B-0D34D19067AB"
REROOT_FILES = {
    DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID,
    PRODUCT_NAME_FILE_PATH: PRODUCT_NAME,
}

VMW_MULTIPLE_KEYS = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAA... test1@vmw.com",
    "ssh-rsa AAAAB3NzaC1yc2EAAAA... test2@vmw.com",
]
VMW_SINGLE_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAA... test@vmw.com"

VMW_METADATA_YAML = """instance-id: cloud-vm
local-hostname: cloud-vm
network:
  version: 2
  ethernets:
    nics:
      match:
        name: ens*
      dhcp4: yes
"""

VMW_USERDATA_YAML = """## template: jinja
#cloud-config
users:
- default
"""

VMW_VENDORDATA_YAML = """## template: jinja
#cloud-config
runcmd:
- echo "Hello, world."
"""


@pytest.fixture(autouse=True)
def common_patches():
    with mock.patch("cloudinit.util.platform.platform", return_value="Linux"):
        with mock.patch.multiple(
            "cloudinit.dmi",
            is_container=mock.Mock(return_value=False),
            is_FreeBSD=mock.Mock(return_value=False),
        ):
            yield


class TestDataSourceVMware(CiTestCase):
    """
    Test common functionality that is not transport specific.
    """

    def setUp(self):
        super(TestDataSourceVMware, self).setUp()
        self.tmp = self.tmp_dir()

    def test_no_data_access_method(self):
        ds = get_ds(self.tmp)
        ds.vmware_rpctool = None
        ret = ds.get_data()
        self.assertFalse(ret)

    def test_get_host_info(self):
        host_info = DataSourceVMware.get_host_info()
        self.assertTrue(host_info)
        self.assertTrue(host_info["hostname"])
        self.assertTrue(host_info["local-hostname"])
        self.assertTrue(host_info["local_hostname"])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4])


class TestDataSourceVMwareEnvVars(FilesystemMockingTestCase):
    """
    Test the envvar transport.
    """

    def setUp(self):
        super(TestDataSourceVMwareEnvVars, self).setUp()
        self.tmp = self.tmp_dir()
        os.environ[DataSourceVMware.VMX_GUESTINFO] = "1"
        self.create_system_files()

    def tearDown(self):
        del os.environ[DataSourceVMware.VMX_GUESTINFO]
        return super(TestDataSourceVMwareEnvVars, self).tearDown()

    def create_system_files(self):
        rootd = self.tmp_dir()
        populate_dir(
            rootd,
            {
                DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID,
            },
        )
        self.assertTrue(self.reRoot(rootd))

    def assert_get_data_ok(self, m_fn, m_fn_call_count=6):
        ds = get_ds(self.tmp)
        ds.vmware_rpctool = None
        ret = ds.get_data()
        self.assertTrue(ret)
        self.assertEqual(m_fn_call_count, m_fn.call_count)
        self.assertEqual(
            ds.data_access_method, DataSourceVMware.DATA_ACCESS_METHOD_ENVVAR
        )
        return ds

    def assert_metadata(self, metadata, m_fn, m_fn_call_count=6):
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count)
        assert_metadata(self, ds, metadata)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_subplatform(self, m_fn):
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count=4)
        self.assertEqual(
            ds.subplatform,
            "%s (%s)"
            % (
                DataSourceVMware.DATA_ACCESS_METHOD_ENVVAR,
                DataSourceVMware.get_guestinfo_envvar_key_name("metadata"),
            ),
        )

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_only(self, m_fn):
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_userdata_only(self, m_fn):
        m_fn.side_effect = ["", VMW_USERDATA_YAML, "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_vendordata_only(self, m_fn):
        m_fn.side_effect = ["", "", VMW_VENDORDATA_YAML, ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_base64(self, m_fn):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_b64(self, m_fn):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_gzip_base64(self, m_fn):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gzip+base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_gz_b64(self, m_fn):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gz+b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_metadata_single_ssh_key(self, m_fn):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_SINGLE_KEY
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_metadata_multiple_ssh_keys(self, m_fn):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_MULTIPLE_KEYS
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)


class TestDataSourceVMwareGuestInfo(FilesystemMockingTestCase):
    """
    Test the guestinfo transport on a VMware platform.
    """

    def setUp(self):
        super(TestDataSourceVMwareGuestInfo, self).setUp()
        self.tmp = self.tmp_dir()
        self.create_system_files()

    def create_system_files(self):
        rootd = self.tmp_dir()
        populate_dir(
            rootd,
            {
                DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID,
                PRODUCT_NAME_FILE_PATH: PRODUCT_NAME,
            },
        )
        self.assertTrue(self.reRoot(rootd))

    def assert_get_data_ok(self, m_fn, m_fn_call_count=6):
        ds = get_ds(self.tmp)
        ds.vmware_rpctool = "vmware-rpctool"
        ret = ds.get_data()
        self.assertTrue(ret)
        self.assertEqual(m_fn_call_count, m_fn.call_count)
        self.assertEqual(
            ds.data_access_method,
            DataSourceVMware.DATA_ACCESS_METHOD_GUESTINFO,
        )
        return ds

    def assert_metadata(self, metadata, m_fn, m_fn_call_count=6):
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count)
        assert_metadata(self, ds, metadata)

    def test_ds_valid_on_vmware_platform(self):
        system_type = dmi.read_dmi_data("system-product-name")
        self.assertEqual(system_type, PRODUCT_NAME)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_subplatform(self, m_fn):
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count=4)
        self.assertEqual(
            ds.subplatform,
            "%s (%s)"
            % (
                DataSourceVMware.DATA_ACCESS_METHOD_GUESTINFO,
                DataSourceVMware.get_guestinfo_key_name("metadata"),
            ),
        )

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_userdata_only(self, m_fn):
        m_fn.side_effect = ["", VMW_USERDATA_YAML, "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_vendordata_only(self, m_fn):
        m_fn.side_effect = ["", "", VMW_VENDORDATA_YAML, ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_metadata_single_ssh_key(self, m_fn):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_SINGLE_KEY
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_metadata_multiple_ssh_keys(self, m_fn):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_MULTIPLE_KEYS
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_metadata_base64(self, m_fn):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_metadata_b64(self, m_fn):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_metadata_gzip_base64(self, m_fn):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gzip+base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_get_data_metadata_gz_b64(self, m_fn):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gz+b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)


class TestDataSourceVMwareGuestInfo_InvalidPlatform(FilesystemMockingTestCase):
    """
    Test the guestinfo transport on a non-VMware platform.
    """

    def setUp(self):
        super(TestDataSourceVMwareGuestInfo_InvalidPlatform, self).setUp()
        self.tmp = self.tmp_dir()
        self.create_system_files()

    def create_system_files(self):
        rootd = self.tmp_dir()
        populate_dir(
            rootd,
            {
                DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID,
            },
        )
        self.assertTrue(self.reRoot(rootd))

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_ds_invalid_on_non_vmware_platform(self, m_fn):
        system_type = dmi.read_dmi_data("system-product-name")
        self.assertEqual(system_type, None)

        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = get_ds(self.tmp)
        ds.vmware_rpctool = "vmware-rpctool"
        ret = ds.get_data()
        self.assertFalse(ret)


def assert_metadata(test_obj, ds, metadata):
    test_obj.assertEqual(metadata.get("instance-id"), ds.get_instance_id())
    test_obj.assertEqual(metadata.get("local-hostname"), ds.get_hostname())

    expected_public_keys = metadata.get("public_keys")
    if not isinstance(expected_public_keys, list):
        expected_public_keys = [expected_public_keys]

    test_obj.assertEqual(expected_public_keys, ds.get_public_ssh_keys())
    test_obj.assertIsInstance(ds.get_public_ssh_keys(), list)


def get_ds(temp_dir):
    ds = DataSourceVMware.DataSourceVMware(
        settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": temp_dir})
    )
    ds.vmware_rpctool = "vmware-rpctool"
    return ds


# vi: ts=4 expandtab
