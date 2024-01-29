# Copyright (c) 2021-2022 VMware, Inc. All Rights Reserved.
#
# Authors: Andrew Kutz <akutz@vmware.com>
#          Pengpeng Sun <pengpengs@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import os
from contextlib import ExitStack
from textwrap import dedent

import pytest

from cloudinit import dmi, helpers, safeyaml, settings, util
from cloudinit.sources import DataSourceVMware
from cloudinit.sources.helpers.vmware.imc import guestcust_util
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    populate_dir,
    wrap_and_call,
)

MPATH = "cloudinit.sources.DataSourceVMware."
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
    mocks = [
        mock.patch("cloudinit.util.platform.platform", return_value="Linux"),
        mock.patch.multiple(
            "cloudinit.dmi",
            is_container=mock.Mock(return_value=False),
            is_FreeBSD=mock.Mock(return_value=False),
        ),
        mock.patch(
            "cloudinit.sources.DataSourceVMware.netifaces.interfaces",
            return_value=[],
        ),
        mock.patch(
            "cloudinit.sources.DataSourceVMware.getfqdn",
            return_value="host.cloudinit.test",
        ),
    ]
    with ExitStack() as stack:
        for some_mock in mocks:
            stack.enter_context(some_mock)
        yield


class TestDataSourceVMware(CiTestCase):
    """
    Test common functionality that is not transport specific.
    """

    with_logs = True

    def setUp(self):
        super(TestDataSourceVMware, self).setUp()
        self.tmp = self.tmp_dir()

    def test_no_data_access_method(self):
        ds = get_ds(self.tmp)
        with mock.patch(
            "cloudinit.sources.DataSourceVMware.is_vmware_platform",
            return_value=False,
        ):
            ret = ds.get_data()
        self.assertFalse(ret)

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_ipv4(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = ("10.10.10.1", None)
        host_info = DataSourceVMware.get_host_info()
        self.assertTrue(host_info)
        self.assertTrue(host_info["hostname"])
        self.assertTrue(host_info["hostname"] == "host.cloudinit.test")
        self.assertTrue(host_info["local-hostname"])
        self.assertTrue(host_info["local_hostname"])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1")
        self.assertFalse(host_info.get(DataSourceVMware.LOCAL_IPV6))

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_ipv6(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = (None, "2001:db8::::::8888")
        host_info = DataSourceVMware.get_host_info()
        self.assertTrue(host_info)
        self.assertTrue(host_info["hostname"])
        self.assertTrue(host_info["hostname"] == "host.cloudinit.test")
        self.assertTrue(host_info["local-hostname"])
        self.assertTrue(host_info["local_hostname"])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV6])
        self.assertTrue(
            host_info[DataSourceVMware.LOCAL_IPV6] == "2001:db8::::::8888"
        )
        self.assertFalse(host_info.get(DataSourceVMware.LOCAL_IPV4))

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_dual(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = ("10.10.10.1", "2001:db8::::::8888")
        host_info = DataSourceVMware.get_host_info()
        self.assertTrue(host_info)
        self.assertTrue(host_info["hostname"])
        self.assertTrue(host_info["hostname"] == "host.cloudinit.test")
        self.assertTrue(host_info["local-hostname"])
        self.assertTrue(host_info["local_hostname"])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1")
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV6])
        self.assertTrue(
            host_info[DataSourceVMware.LOCAL_IPV6] == "2001:db8::::::8888"
        )

    @mock.patch("cloudinit.sources.DataSourceVMware.get_host_info")
    def test_wait_on_network(self, m_fn):
        metadata = {
            DataSourceVMware.WAIT_ON_NETWORK: {
                DataSourceVMware.WAIT_ON_NETWORK_IPV4: True,
                DataSourceVMware.WAIT_ON_NETWORK_IPV6: False,
            },
        }
        m_fn.side_effect = [
            {
                "hostname": "host.cloudinit.test",
                "local-hostname": "host.cloudinit.test",
                "local_hostname": "host.cloudinit.test",
                "network": {
                    "interfaces": {
                        "by-ipv4": {},
                        "by-ipv6": {},
                        "by-mac": {
                            "aa:bb:cc:dd:ee:ff": {"ipv4": [], "ipv6": []}
                        },
                    },
                },
            },
            {
                "hostname": "host.cloudinit.test",
                "local-hostname": "host.cloudinit.test",
                "local-ipv4": "10.10.10.1",
                "local_hostname": "host.cloudinit.test",
                "network": {
                    "interfaces": {
                        "by-ipv4": {
                            "10.10.10.1": {
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "netmask": "255.255.255.0",
                            }
                        },
                        "by-mac": {
                            "aa:bb:cc:dd:ee:ff": {
                                "ipv4": [
                                    {
                                        "addr": "10.10.10.1",
                                        "broadcast": "10.10.10.255",
                                        "netmask": "255.255.255.0",
                                    }
                                ],
                                "ipv6": [],
                            }
                        },
                    },
                },
            },
        ]

        host_info = DataSourceVMware.wait_on_network(metadata)

        logs = self.logs.getvalue()
        expected_logs = [
            "DEBUG: waiting on network: wait4=True, "
            "ready4=False, wait6=False, ready6=False\n",
            "DEBUG: waiting on network complete\n",
        ]
        for log in expected_logs:
            self.assertIn(log, logs)

        self.assertTrue(host_info)
        self.assertTrue(host_info["hostname"])
        self.assertTrue(host_info["hostname"] == "host.cloudinit.test")
        self.assertTrue(host_info["local-hostname"])
        self.assertTrue(host_info["local_hostname"])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4])
        self.assertTrue(host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1")


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
        return super().tearDown()

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
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_subplatform(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
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
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_with_vmware_rpctool(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.exec_vmware_rpctool")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_non_zero_exit_code_fallback_to_vmtoolsd(
        self, m_which_fn, m_exec_vmware_rpctool_fn, m_fn
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_exec_vmware_rpctool_fn.side_effect = ProcessExecutionError(
            exit_code=1
        )
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.exec_vmware_rpctool")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_vmware_rpctool_not_found_fallback_to_vmtoolsd(
        self, m_which_fn, m_exec_vmware_rpctool_fn, m_fn
    ):
        m_which_fn.side_effect = ["vmtoolsd", None]
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_userdata_only(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_fn.side_effect = ["", VMW_USERDATA_YAML, "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_vendordata_only(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_fn.side_effect = ["", "", VMW_VENDORDATA_YAML, ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_metadata_single_ssh_key(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_SINGLE_KEY
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_metadata_multiple_ssh_keys(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_MULTIPLE_KEYS
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_base64(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_b64(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_gzip_base64(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gzip+base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_gz_b64(self, m_which_fn, m_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
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
        ret = ds.get_data()
        self.assertFalse(ret)


class TestDataSourceVMwareIMC(CiTestCase):
    """
    Test the VMware Guest OS Customization transport
    """

    with_logs = True

    def setUp(self):
        super(TestDataSourceVMwareIMC, self).setUp()
        self.datasource = DataSourceVMware.DataSourceVMware
        self.tdir = self.tmp_dir()

    def test_get_data_false_on_none_dmi_data(self):
        """When dmi for system-product-name is None, get_data returns False."""
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)
        result = wrap_and_call(
            "cloudinit.sources.DataSourceVMware",
            {
                "dmi.read_dmi_data": None,
            },
            ds.get_data,
        )
        self.assertFalse(result, "Expected False return from ds.get_data")
        self.assertIn("No system-product-name found", self.logs.getvalue())

    def test_get_imc_data_vmware_customization_disabled(self):
        """
        When vmware customization is disabled via sys_cfg and
        allow_raw_data is disabled via ds_cfg, log a message.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"VMware": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        result = wrap_and_call(
            "cloudinit.sources.DataSourceVMware",
            {
                "dmi.read_dmi_data": "vmware",
            },
            ds.get_imc_data_fn,
        )
        self.assertEqual(result, (None, None, None))
        self.assertIn(
            "Customization for VMware platform is disabled",
            self.logs.getvalue(),
        )

    def test_get_imc_data_vmware_customization_sys_cfg_disabled(self):
        """
        When vmware customization is disabled via sys_cfg and
        no meta data is found, log a message.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"VMware": {"allow_raw_data": True}},
            },
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        result = wrap_and_call(
            "cloudinit.sources.DataSourceVMware",
            {
                "dmi.read_dmi_data": "vmware",
                "util.del_dir": True,
                "guestcust_util.search_file": self.tdir,
                "guestcust_util.wait_for_cust_cfg_file": conf_file,
            },
            ds.get_imc_data_fn,
        )
        self.assertEqual(result, (None, None, None))
        self.assertIn(
            "No allowed customization configuration data found",
            self.logs.getvalue(),
        )

    def test_get_imc_data_allow_raw_data_disabled(self):
        """
        When allow_raw_data is disabled via ds_cfg and
        meta data is found, log a message.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": False,
                "datasource": {"VMware": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        result = wrap_and_call(
            "cloudinit.sources.DataSourceVMware",
            {
                "dmi.read_dmi_data": "vmware",
                "util.del_dir": True,
                "guestcust_util.search_file": self.tdir,
                "guestcust_util.wait_for_cust_cfg_file": conf_file,
            },
            ds.get_imc_data_fn,
        )
        self.assertEqual(result, (None, None, None))
        self.assertIn(
            "No allowed customization configuration data found",
            self.logs.getvalue(),
        )

    def test_get_imc_data_vmware_customization_enabled(self):
        """
        When cloud-init workflow for vmware is enabled via sys_cfg log a
        message.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        with mock.patch(
            MPATH + "guestcust_util.get_tools_config",
            return_value="true",
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                },
                ds.get_imc_data_fn,
            )
            self.assertEqual(result, (None, None, None))
        custom_script = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % custom_script,
            self.logs.getvalue(),
        )

    def test_get_imc_data_cust_script_disabled(self):
        """
        If custom script is disabled by VMware tools configuration,
        log a message.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the custom sript
        customscript = self.tmp_path("test-script", self.tdir)
        util.write_file(customscript, "This is the post cust script")

        with mock.patch(
            MPATH + "guestcust_util.get_tools_config",
            return_value="invalid",
        ):
            with mock.patch(
                MPATH + "guestcust_util.set_customization_status",
                return_value=("msg", b""),
            ):
                result = wrap_and_call(
                    "cloudinit.sources.DataSourceVMware",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "guestcust_util.search_file": self.tdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                self.assertEqual(result, (None, None, None))
        self.assertIn(
            "Custom script is disabled by VM Administrator",
            self.logs.getvalue(),
        )

    def test_get_imc_data_cust_script_enabled(self):
        """
        If custom script is enabled by VMware tools configuration,
        execute the script.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            """
        )
        util.write_file(conf_file, conf_content)

        # Mock custom script is enabled by return true when calling
        # get_tools_config
        with mock.patch(
            MPATH + "guestcust_util.get_tools_config",
            return_value="true",
        ):
            with mock.patch(
                MPATH + "guestcust_util.set_customization_status",
                return_value=("msg", b""),
            ):
                result = wrap_and_call(
                    "cloudinit.sources.DataSourceVMware",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "guestcust_util.search_file": self.tdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                self.assertEqual(result, (None, None, None))
        # Verify custom script is trying to be executed
        custom_script = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % custom_script,
            self.logs.getvalue(),
        )

    def test_get_imc_data_force_run_post_script_is_yes(self):
        """
        If DEFAULT-RUN-POST-CUST-SCRIPT is yes, custom script could run if
        enable-custom-scripts is not defined in VM Tools configuration
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        # set DEFAULT-RUN-POST-CUST-SCRIPT = yes so that enable-custom-scripts
        # default value is TRUE
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            DEFAULT-RUN-POST-CUST-SCRIPT = yes
            """
        )
        util.write_file(conf_file, conf_content)

        # Mock get_tools_config(section, key, defaultVal) to return
        # defaultVal
        def my_get_tools_config(*args, **kwargs):
            return args[2]

        with mock.patch(
            MPATH + "guestcust_util.get_tools_config",
            side_effect=my_get_tools_config,
        ):
            with mock.patch(
                MPATH + "guestcust_util.set_customization_status",
                return_value=("msg", b""),
            ):
                result = wrap_and_call(
                    "cloudinit.sources.DataSourceVMware",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "guestcust_util.search_file": self.tdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                self.assertEqual(result, (None, None, None))
        # Verify custom script still runs although it is
        # disabled by VMware Tools
        custom_script = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % custom_script,
            self.logs.getvalue(),
        )

    def test_get_data_cloudinit_metadata_json(self):
        """
        Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is json.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            {
              "instance-id": "cloud-vm",
              "local-hostname": "my-host.domain.com",
              "network": {
                "version": 2,
                "ethernets": {
                  "eths": {
                    "match": {
                      "name": "ens*"
                    },
                    "dhcp4": true
                  }
                }
              }
            }
            """
        )
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds._get_data,
            )
            self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual("my-host.domain.com", ds.metadata["local-hostname"])
        self.assertEqual(2, ds.network_config["version"])
        self.assertTrue(ds.network_config["ethernets"]["eths"]["dhcp4"])

    def test_get_data_cloudinit_metadata_yaml(self):
        """
        Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is yaml.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds._get_data,
            )
            self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual("my-host.domain.com", ds.metadata["local-hostname"])
        self.assertEqual(2, ds.network_config["version"])
        self.assertTrue(ds.network_config["ethernets"]["nics"]["dhcp4"])

    def test_get_imc_data_cloudinit_metadata_not_valid(self):
        """
        Test metadata is not JSON or YAML format, log a message
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = "[This is not json or yaml format]a=b"
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds.get_data,
            )
        self.assertFalse(result)
        self.assertIn(
            "expected '<document start>', but found '<scalar>'",
            self.logs.getvalue(),
        )

    def test_get_imc_data_cloudinit_metadata_not_found(self):
        """
        Test metadata file can't be found, log a message
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Don't prepare the meta data file

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds.get_imc_data_fn,
            )
            self.assertEqual(result, (None, None, None))
        self.assertIn("Meta data file is not found", self.logs.getvalue())

    def test_get_data_cloudinit_userdata(self):
        """
        Test user data can be loaded to cloud-init user data.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        # Prepare the user data file
        userdata_file = self.tmp_path("test-user", self.tdir)
        userdata_content = "This is the user data"
        util.write_file(userdata_file, userdata_content)

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds._get_data,
            )
            self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual(userdata_content, ds.userdata_raw)

    def test_get_imc_data_cloudinit_userdata_not_found(self):
        """
        Test userdata file can't be found.
        """
        paths = helpers.Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        # Don't prepare the user data file

        with mock.patch(
            MPATH + "guestcust_util.set_customization_status",
            return_value=("msg", b""),
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceVMware",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "guestcust_util.search_file": self.tdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": self.tdir,
                },
                ds.get_imc_data_fn,
            )
            self.assertEqual(result, (None, None, None))
        self.assertIn("Userdata file is not found", self.logs.getvalue())


class TestDataSourceVMwareIMC_MarkerFiles(CiTestCase):
    def setUp(self):
        super(TestDataSourceVMwareIMC_MarkerFiles, self).setUp()
        self.tdir = self.tmp_dir()

    def test_false_when_markerid_none(self):
        """Return False when markerid provided is None."""
        self.assertFalse(
            guestcust_util.check_marker_exists(
                markerid=None, marker_dir=self.tdir
            )
        )

    def test_markerid_file_exist(self):
        """Return False when markerid file path does not exist,
        True otherwise."""
        self.assertFalse(guestcust_util.check_marker_exists("123", self.tdir))
        marker_file = self.tmp_path(".markerfile-123.txt", self.tdir)
        util.write_file(marker_file, "")
        self.assertTrue(guestcust_util.check_marker_exists("123", self.tdir))

    def test_marker_file_setup(self):
        """Test creation of marker files."""
        markerfilepath = self.tmp_path(".markerfile-hi.txt", self.tdir)
        self.assertFalse(os.path.exists(markerfilepath))
        guestcust_util.setup_marker_files(marker_id="hi", marker_dir=self.tdir)
        self.assertTrue(os.path.exists(markerfilepath))


def assert_metadata(test_obj, ds, metadata):
    test_obj.assertEqual(metadata.get("instance-id"), ds.get_instance_id())
    test_obj.assertEqual(
        metadata.get("local-hostname"), ds.get_hostname().hostname
    )

    expected_public_keys = metadata.get("public_keys")
    if not isinstance(expected_public_keys, list):
        expected_public_keys = [expected_public_keys]

    test_obj.assertEqual(expected_public_keys, ds.get_public_ssh_keys())
    test_obj.assertIsInstance(ds.get_public_ssh_keys(), list)


def get_ds(temp_dir):
    ds = DataSourceVMware.DataSourceVMware(
        settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": temp_dir})
    )
    return ds
