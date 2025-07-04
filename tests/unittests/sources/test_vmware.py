# Copyright (c) 2021-2025 Broadcom. All Rights Reserved.
#
# Authors: Andrew Kutz <andrew.kutz@broadcom.com>
#          Pengpeng Sun <pengpeng.sun@broadcom.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import os
from contextlib import ExitStack
from logging import DEBUG
from textwrap import dedent

import pytest

from cloudinit import dmi, helpers, safeyaml, settings, util
from cloudinit.event import EventScope
from cloudinit.sources import DataSourceVMware
from cloudinit.sources.helpers.vmware.imc import guestcust_util
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import mock, populate_dir, wrap_and_call

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

VMW_METADATA_YAML = """\
instance-id: cloud-vm
local-hostname: cloud-vm
network:
  version: 2
  ethernets:
    nics:
      match:
        name: ens*
      dhcp4: yes
"""

VMW_USERDATA_YAML = """\
## template: jinja
#cloud-config
users:
- default
"""

VMW_VENDORDATA_YAML = """\
## template: jinja
#cloud-config
runcmd:
- echo "Hello, world."
"""

VMW_IPV4_ROUTEINFO = {
    "destination": "0.0.0.0",
    "flags": "G",
    "gateway": "10.85.130.1",
    "genmask": "0.0.0.0",
    "iface": "eth0",
    "metric": "50",
}
VMW_IPV4_NETDEV_ADDR = {
    "bcast": "10.85.130.255",
    "ip": "10.85.130.116",
    "mask": "255.255.255.0",
    "scope": "global",
}
VMW_IPV4_NETIFACES_ADDR = {
    "broadcast": "10.85.130.255",
    "netmask": "255.255.255.0",
    "addr": "10.85.130.116",
}
VMW_IPV6_ROUTEINFO = {
    "destination": "::/0",
    "flags": "UG",
    "gateway": "2001:67c:1562:8007::1",
    "iface": "eth0",
    "metric": "50",
}
VMW_IPV6_NETDEV_ADDR = {
    "ip": "fd42:baa2:3dd:17a:216:3eff:fe16:db54/64",
    "scope6": "global",
}
VMW_IPV6_NETIFACES_ADDR = {
    "netmask": "ffff:ffff:ffff:ffff::/64",
    "addr": "fd42:baa2:3dd:17a:216:3eff:fe16:db54",
}
VMW_IPV6_NETDEV_PEER_ADDR = {
    "ip": "fd42:baa2:3dd:17a:216:3eff:fe16:db54",
    "scope6": "global",
}
VMW_IPV6_NETIFACES_PEER_ADDR = {
    "netmask": "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff/128",
    "addr": "fd42:baa2:3dd:17a:216:3eff:fe16:db54",
}

# Please note this should be a constant, but uses formatting to avoid
# the line-length warning from the linter.
VMW_EXPECTED_EXTRA_HOTPLUG_UDEV_RULES = """
ENV{ID_NET_DRIVER}=="e1000|e1000e|vlance|vmxnet2|vmxnet3|vrdma", GOTO="cloudinit_hook"
GOTO="cloudinit_end"
"""  # noqa: E501


VMW_METADATA_YAML_WITH_NET_DRIVERS = """\
instance-id: cloud-vm
local-hostname: cloud-vm
network-drivers:
- vmxnet2
- vmxnet3
"""

VMW_EXPECTED_EXTRA_HOTPLUG_UDEV_RULES_VMXNET = """
ENV{ID_NET_DRIVER}=="vmxnet2|vmxnet3", GOTO="cloudinit_hook"
GOTO="cloudinit_end"
"""


def generate_test_netdev_data(ipv4=None, ipv6=None):
    ipv4 = ipv4 or []
    ipv6 = ipv6 or []
    return {
        "eth0": {
            "hwaddr": "00:16:3e:16:db:54",
            "ipv4": ipv4,
            "ipv6": ipv6,
            "up": True,
        },
    }


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
            "cloudinit.netinfo.netdev_info",
            return_value={},
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


class TestDataSourceVMware:
    """
    Test common functionality that is not transport specific.
    """

    def test_no_data_access_method(self):
        ds = get_ds()
        with mock.patch(
            "cloudinit.sources.DataSourceVMware.is_vmware_platform",
            return_value=False,
        ):
            ret = ds.get_data()
        assert not ret

    def test_convert_to_netifaces_ipv4_format(self):
        netifaces_format = DataSourceVMware.convert_to_netifaces_ipv4_format(
            VMW_IPV4_NETDEV_ADDR
        )
        assert netifaces_format == VMW_IPV4_NETIFACES_ADDR

    def test_convert_to_netifaces_ipv6_format(self):
        netifaces_format = DataSourceVMware.convert_to_netifaces_ipv6_format(
            VMW_IPV6_NETDEV_ADDR
        )
        assert netifaces_format == VMW_IPV6_NETIFACES_ADDR
        netifaces_format = DataSourceVMware.convert_to_netifaces_ipv6_format(
            VMW_IPV6_NETDEV_PEER_ADDR
        )
        assert netifaces_format == VMW_IPV6_NETIFACES_PEER_ADDR

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_ipv4(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = ("10.10.10.1", None)
        host_info = DataSourceVMware.get_host_info()
        assert host_info
        assert host_info["hostname"]
        assert host_info["hostname"] == "host.cloudinit.test"
        assert host_info["local-hostname"]
        assert host_info["local_hostname"]
        assert host_info[DataSourceVMware.LOCAL_IPV4]
        assert host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1"
        assert not host_info.get(DataSourceVMware.LOCAL_IPV6)

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_ipv6(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = (None, "2001:db8::::::8888")
        host_info = DataSourceVMware.get_host_info()
        assert host_info
        assert host_info["hostname"]
        assert host_info["hostname"] == "host.cloudinit.test"
        assert host_info["local-hostname"]
        assert host_info["local_hostname"]
        assert host_info[DataSourceVMware.LOCAL_IPV6]
        assert host_info[DataSourceVMware.LOCAL_IPV6] == "2001:db8::::::8888"
        assert not host_info.get(DataSourceVMware.LOCAL_IPV4)

    @mock.patch("cloudinit.sources.DataSourceVMware.get_default_ip_addrs")
    def test_get_host_info_dual(self, m_fn_ipaddr):
        m_fn_ipaddr.return_value = ("10.10.10.1", "2001:db8::::::8888")
        host_info = DataSourceVMware.get_host_info()
        assert host_info
        assert host_info["hostname"]
        assert host_info["hostname"] == "host.cloudinit.test"
        assert host_info["local-hostname"]
        assert host_info["local_hostname"]
        assert host_info[DataSourceVMware.LOCAL_IPV4]
        assert host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1"
        assert host_info[DataSourceVMware.LOCAL_IPV6]
        assert host_info[DataSourceVMware.LOCAL_IPV6] == "2001:db8::::::8888"

    # TODO migrate this entire test suite to pytest then parameterize
    @mock.patch("cloudinit.netinfo.route_info")
    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_get_default_ip_addrs_ipv4only(
        self,
        m_netdev_info,
        m_route_info,
    ):
        """Test get_default_ip_addrs use cases"""
        m_route_info.return_value = {
            "ipv4": [VMW_IPV4_ROUTEINFO],
            "ipv6": [],
        }
        m_netdev_info.return_value = generate_test_netdev_data(
            ipv4=[VMW_IPV4_NETDEV_ADDR]
        )
        ipv4, ipv6 = DataSourceVMware.get_default_ip_addrs()
        assert ipv4 == "10.85.130.116"
        assert ipv6 is None

    @mock.patch("cloudinit.netinfo.route_info")
    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_get_default_ip_addrs_ipv6only(
        self,
        m_netdev_info,
        m_route_info,
    ):
        m_route_info.return_value = {
            "ipv4": [],
            "ipv6": [VMW_IPV6_ROUTEINFO],
        }
        m_netdev_info.return_value = generate_test_netdev_data(
            ipv6=[VMW_IPV6_NETDEV_ADDR]
        )
        ipv4, ipv6 = DataSourceVMware.get_default_ip_addrs()
        assert ipv4 is None
        assert ipv6 == "fd42:baa2:3dd:17a:216:3eff:fe16:db54/64"

    @mock.patch("cloudinit.netinfo.route_info")
    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_get_default_ip_addrs_dualstack(
        self,
        m_netdev_info,
        m_route_info,
    ):
        m_route_info.return_value = {
            "ipv4": [VMW_IPV4_ROUTEINFO],
            "ipv6": [VMW_IPV6_ROUTEINFO],
        }
        m_netdev_info.return_value = generate_test_netdev_data(
            ipv4=[VMW_IPV4_NETDEV_ADDR],
            ipv6=[VMW_IPV6_NETDEV_ADDR],
        )
        ipv4, ipv6 = DataSourceVMware.get_default_ip_addrs()
        assert ipv4 == "10.85.130.116"
        assert ipv6 == "fd42:baa2:3dd:17a:216:3eff:fe16:db54/64"

    @mock.patch("cloudinit.netinfo.route_info")
    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_get_default_ip_addrs_multiaddr(
        self,
        m_netdev_info,
        m_route_info,
    ):
        m_route_info.return_value = {
            "ipv4": [VMW_IPV4_ROUTEINFO],
            "ipv6": [],
        }
        m_netdev_info.return_value = generate_test_netdev_data(
            ipv4=[
                VMW_IPV4_NETDEV_ADDR,
                {
                    "bcast": "10.85.131.255",
                    "ip": "10.85.131.117",
                    "mask": "255.255.255.0",
                    "scope": "global",
                },
            ],
            ipv6=[
                VMW_IPV6_NETDEV_ADDR,
                {
                    "ip": "fe80::216:3eff:fe16:db54/64",
                    "scope6": "link",
                },
            ],
        )
        ipv4, ipv6 = DataSourceVMware.get_default_ip_addrs()
        assert ipv4 is None
        assert ipv6 is None

    @mock.patch("cloudinit.netinfo.route_info")
    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_get_default_ip_addrs_nodefault(
        self,
        m_netdev_info,
        m_route_info,
    ):
        m_route_info.return_value = {
            "ipv4": [
                {
                    "destination": "185.125.188.0",
                    "flags": "G",
                    "gateway": "10.85.130.1",
                    "genmask": "0.0.0.255",
                    "iface": "eth0",
                    "metric": "50",
                },
            ],
            "ipv6": [],
        }
        m_netdev_info.return_value = generate_test_netdev_data(
            ipv4=[VMW_IPV4_NETDEV_ADDR],
            ipv6=[VMW_IPV6_NETDEV_ADDR],
        )
        ipv4, ipv6 = DataSourceVMware.get_default_ip_addrs()
        assert ipv4 is None
        assert ipv6 is None

    @mock.patch("cloudinit.sources.DataSourceVMware.get_host_info")
    def test_wait_on_network(self, m_fn, caplog):
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

        expected_logs = [
            (
                "cloudinit.sources.DataSourceVMware",
                DEBUG,
                (
                    "waiting on network: wait4=True, "
                    "ready4=False, wait6=False, ready6=False"
                ),
            ),
            (
                "cloudinit.sources.DataSourceVMware",
                DEBUG,
                "waiting on network complete",
            ),
        ]
        for log in expected_logs:
            assert log in caplog.record_tuples

        assert host_info
        assert host_info["hostname"]
        assert host_info["hostname"] == "host.cloudinit.test"
        assert host_info["local-hostname"]
        assert host_info["local_hostname"]
        assert host_info[DataSourceVMware.LOCAL_IPV4]
        assert host_info[DataSourceVMware.LOCAL_IPV4] == "10.10.10.1"

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_set_value")
    def test_advertise_update_events(self, m_set_fn):
        (
            supported_events,
            enabled_events,
        ) = DataSourceVMware.advertise_update_events(
            DataSourceVMware.SUPPORTED_UPDATE_EVENTS,
            DataSourceVMware.DEFAULT_UPDATE_EVENTS,
            "rpctool",
            len,
        )
        assert 2 == m_set_fn.call_count
        assert "network=boot;boot-new-instance;hotplug" == supported_events
        assert "network=boot-new-instance;hotplug" == enabled_events

    def test_extra_hotplug_udev_rules(self):
        ds = get_ds()
        assert (
            VMW_EXPECTED_EXTRA_HOTPLUG_UDEV_RULES
            == ds.extra_hotplug_udev_rules
        )


class TestDataSourceVMwareEnvVars:
    """
    Test the envvar transport.
    """

    @pytest.fixture(autouse=True)
    def env_and_files(
        self,
        fake_filesystem,
        monkeypatch,
        tmpdir,
    ):
        monkeypatch.setenv(DataSourceVMware.VMX_GUESTINFO, "1")
        populate_dir(
            str(tmpdir),
            {DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID},
        )

    def assert_get_data_ok(self, m_fn, m_fn_call_count=6):
        ds = get_ds()
        ret = ds.get_data()
        assert ret
        assert m_fn_call_count == m_fn.call_count
        assert (
            ds.data_access_method == DataSourceVMware.DATA_ACCESS_METHOD_ENVVAR
        )
        return ds

    def assert_metadata(self, metadata, m_fn, m_fn_call_count=6):
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count)
        assert_metadata(ds, metadata)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_subplatform(
        self,
        m_fn,
    ):
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count=4)
        assert ds.subplatform == "%s (%s)" % (
            DataSourceVMware.DATA_ACCESS_METHOD_ENVVAR,
            DataSourceVMware.get_guestinfo_envvar_key_name("metadata"),
        )

        # Test to ensure that network is configured from metadata on each boot.
        assert (
            DataSourceVMware.DEFAULT_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.default_update_events[EventScope.NETWORK]
        )
        assert (
            DataSourceVMware.SUPPORTED_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.supported_update_events[EventScope.NETWORK]
        )

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_only(
        self,
        m_fn,
    ):
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_userdata_only(
        self,
        m_fn,
    ):
        m_fn.side_effect = ["", VMW_USERDATA_YAML, "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_vendordata_only(
        self,
        m_fn,
    ):
        m_fn.side_effect = ["", "", VMW_VENDORDATA_YAML, ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_base64(
        self,
        m_fn,
    ):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_b64(
        self,
        m_fn,
    ):
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_gzip_base64(
        self,
        m_fn,
    ):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gzip+base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_get_data_metadata_gz_b64(
        self,
        m_fn,
    ):
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gz+b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_metadata_single_ssh_key(
        self,
        m_fn,
    ):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_SINGLE_KEY
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch(
        "cloudinit.sources.DataSourceVMware.guestinfo_envvar_get_value"
    )
    def test_metadata_multiple_ssh_keys(
        self,
        m_fn,
    ):
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_MULTIPLE_KEYS
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)


class TestDataSourceVMwareGuestInfo:
    """
    Test the guestinfo transport on a VMware platform.
    """

    @pytest.fixture(autouse=True)
    def create_files(
        self,
        fake_filesystem,
        tmpdir,
    ):
        populate_dir(
            str(tmpdir),
            {
                DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID,
                PRODUCT_NAME_FILE_PATH: PRODUCT_NAME,
            },
        )

    def assert_get_data_ok(self, m_fn, m_fn_call_count=6):
        ds = get_ds()
        ret = ds.get_data()
        assert ret
        assert m_fn_call_count == m_fn.call_count
        assert (
            ds.data_access_method
            == DataSourceVMware.DATA_ACCESS_METHOD_GUESTINFO
        )
        return ds

    def assert_metadata(self, metadata, m_fn, m_fn_call_count=6):
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count)
        assert_metadata(ds, metadata)

    def test_ds_valid_on_vmware_platform(self):
        system_type = dmi.read_dmi_data("system-product-name")
        assert system_type == PRODUCT_NAME

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_subplatform(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_fn, m_fn_call_count=4)
        assert ds.subplatform == "%s (%s)" % (
            DataSourceVMware.DATA_ACCESS_METHOD_GUESTINFO,
            DataSourceVMware.get_guestinfo_key_name("metadata"),
        )

        # Test to ensure that network is configured from metadata on each boot.
        assert (
            DataSourceVMware.DEFAULT_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.default_update_events[EventScope.NETWORK]
        )
        assert (
            DataSourceVMware.SUPPORTED_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.supported_update_events[EventScope.NETWORK]
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
    def test_get_data_userdata_only(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_fn.side_effect = ["", VMW_USERDATA_YAML, "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_vendordata_only(
        self,
        m_which_fn,
        m_fn,
    ):
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
    def test_metadata_multiple_ssh_keys(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        metadata = DataSourceVMware.load_json_or_yaml(VMW_METADATA_YAML)
        metadata["public_keys"] = VMW_MULTIPLE_KEYS
        metadata_yaml = safeyaml.dumps(metadata)
        m_fn.side_effect = [metadata_yaml, "", "", ""]
        self.assert_metadata(metadata, m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_base64(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_b64(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = base64.b64encode(VMW_METADATA_YAML.encode("utf-8"))
        m_fn.side_effect = [data, "b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_gzip_base64(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gzip+base64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_get_data_metadata_gz_b64(
        self,
        m_which_fn,
        m_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        data = VMW_METADATA_YAML.encode("utf-8")
        data = gzip.compress(data)
        data = base64.b64encode(data)
        m_fn.side_effect = [data, "gz+b64", "", ""]
        self.assert_get_data_ok(m_fn, m_fn_call_count=4)

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_set_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_advertise_update_events(self, m_which_fn, m_get_fn, m_set_fn):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_get_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_get_fn, m_fn_call_count=4)
        supported_events, enabled_events = ds.advertise_update_events({})
        assert 2 == m_set_fn.call_count
        assert "network=boot;boot-new-instance;hotplug" == supported_events
        assert "network=boot-new-instance;hotplug" == enabled_events

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_set_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_advertise_update_events_with_events_from_user_data(
        self, m_which_fn, m_get_fn, m_set_fn
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_get_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = self.assert_get_data_ok(m_get_fn, m_fn_call_count=4)
        supported_events, enabled_events = ds.advertise_update_events(
            {
                "updates": {
                    "network": {
                        "when": ["boot"],
                    },
                },
            }
        )
        assert 2 == m_set_fn.call_count
        assert "network=boot;boot-new-instance;hotplug" == supported_events
        assert "network=boot" == enabled_events

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    @mock.patch("cloudinit.sources.DataSourceVMware.which")
    def test_extra_hotplug_udev_rules_with_net_drivers(
        self,
        m_which_fn,
        m_get_fn,
    ):
        m_which_fn.side_effect = ["vmtoolsd", "vmware-rpctool"]
        m_get_fn.side_effect = [
            VMW_METADATA_YAML_WITH_NET_DRIVERS,
            "",
            "",
            "",
            "",
            "",
        ]
        ds = self.assert_get_data_ok(m_get_fn, m_fn_call_count=4)
        ds.init_extra_hotplug_udev_rules()

        assert (
            VMW_EXPECTED_EXTRA_HOTPLUG_UDEV_RULES_VMXNET
            == ds.extra_hotplug_udev_rules
        )


class TestDataSourceVMwareGuestInfo_InvalidPlatform:
    """
    Test the guestinfo transport on a non-VMware platform.
    """

    @pytest.fixture(autouse=True)
    def create_files(
        self,
        fake_filesystem,
        tmpdir,
    ):
        populate_dir(
            str(tmpdir),
            {DataSourceVMware.PRODUCT_UUID_FILE_PATH: PRODUCT_UUID},
        )

    @mock.patch("cloudinit.sources.DataSourceVMware.guestinfo_get_value")
    def test_ds_invalid_on_non_vmware_platform(
        self,
        m_fn,
    ):
        system_type = dmi.read_dmi_data("system-product-name")
        assert system_type is None

        m_fn.side_effect = [VMW_METADATA_YAML, "", "", "", "", ""]
        ds = get_ds()
        ret = ds.get_data()
        assert not ret


class TestDataSourceVMwareIMC:
    """
    Test the VMware Guest OS Customization transport
    """

    datasource = DataSourceVMware.DataSourceVMware

    def test_get_subplatform(self, tmpdir):
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds._get_data,
            )
            assert result

        assert ds.subplatform == "%s (%s)" % (
            DataSourceVMware.DATA_ACCESS_METHOD_IMC,
            DataSourceVMware.get_imc_key_name("metadata"),
        )

        # Test to ensure that network is configured from metadata on each boot.
        assert (
            DataSourceVMware.DEFAULT_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.default_update_events[EventScope.NETWORK]
        )
        assert (
            DataSourceVMware.SUPPORTED_UPDATE_EVENTS[EventScope.NETWORK]
            == ds.supported_update_events[EventScope.NETWORK]
        )

    def test_get_data_false_on_none_dmi_data(self, caplog, tmpdir):
        """When dmi for system-product-name is None, get_data returns False."""
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)
        result = wrap_and_call(
            "cloudinit.sources.DataSourceVMware",
            {
                "dmi.read_dmi_data": None,
            },
            ds.get_data,
        )
        assert not result, "Expected False return from ds.get_data"
        assert "No system-product-name found" in caplog.text

    def test_get_imc_data_vmware_customization_disabled(self, caplog, tmpdir):
        """
        When vmware customization is disabled via sys_cfg and
        allow_raw_data is disabled via ds_cfg, log a message.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"VMware": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )
        conf_file = os.path.join(tmpdir, "test-cust")
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
        assert result == (None, None, None)
        assert "Customization for VMware platform is disabled" in caplog.text

    def test_get_imc_data_vmware_customization_sys_cfg_disabled(
        self, caplog, tmpdir
    ):
        """
        When vmware customization is disabled via sys_cfg and
        no meta data is found, log a message.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"VMware": {"allow_raw_data": True}},
            },
            distro={},
            paths=paths,
        )
        conf_file = os.path.join(tmpdir, "test-cust")
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
                "guestcust_util.search_file": tmpdir,
                "guestcust_util.wait_for_cust_cfg_file": conf_file,
            },
            ds.get_imc_data_fn,
        )
        assert result == (None, None, None)
        assert (
            "No allowed customization configuration data found" in caplog.text
        )

    def test_get_imc_data_allow_raw_data_disabled(self, caplog, tmpdir):
        """
        When allow_raw_data is disabled via ds_cfg and
        meta data is found, log a message.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": False,
                "datasource": {"VMware": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
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
                "guestcust_util.search_file": tmpdir,
                "guestcust_util.wait_for_cust_cfg_file": conf_file,
            },
            ds.get_imc_data_fn,
        )
        assert result == (None, None, None)
        assert (
            "No allowed customization configuration data found" in caplog.text
        )

    @pytest.mark.allow_subp_for("vmware-rpctool")
    def test_get_imc_data_vmware_customization_enabled(self, caplog, tmpdir):
        """
        When cloud-init workflow for vmware is enabled via sys_cfg log a
        message.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        conf_file = os.path.join(tmpdir, "test-cust")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                },
                ds.get_imc_data_fn,
            )
            assert result == (None, None, None)
        custom_script = os.path.join(tmpdir, "test-script")
        assert "Script %s not found!!" % custom_script in caplog.text

    def test_get_imc_data_cust_script_disabled(self, caplog, tmpdir):
        """
        If custom script is disabled by VMware tools configuration,
        log a message.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
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
        customscript = os.path.join(tmpdir, "test-script")
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
                        "guestcust_util.search_file": tmpdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                assert result == (None, None, None)
        assert "Custom script is disabled by VM Administrator" in caplog.text

    def test_get_imc_data_cust_script_enabled(self, caplog, tmpdir):
        """
        If custom script is enabled by VMware tools configuration,
        execute the script.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
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
                        "guestcust_util.search_file": tmpdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                assert result == (None, None, None)
        # Verify custom script is trying to be executed
        custom_script = os.path.join(tmpdir, "test-script")
        assert "Script %s not found!!" % custom_script in caplog.text

    def test_get_imc_data_force_run_post_script_is_yes(self, caplog, tmpdir):
        """
        If DEFAULT-RUN-POST-CUST-SCRIPT is yes, custom script could run if
        enable-custom-scripts is not defined in VM Tools configuration
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
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
                        "guestcust_util.search_file": tmpdir,
                        "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    },
                    ds.get_imc_data_fn,
                )
                assert result == (None, None, None)
        # Verify custom script still runs although it is
        # disabled by VMware Tools
        custom_script = os.path.join(tmpdir, "test-script")
        assert "Script %s not found!!" % custom_script in caplog.text

    def test_get_data_cloudinit_metadata_json(self, tmpdir):
        """
        Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is json.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds._get_data,
            )
            assert result
        assert "cloud-vm" == ds.metadata["instance-id"]
        assert "my-host.domain.com" == ds.metadata["local-hostname"]
        assert 2 == ds.network_config["version"]
        assert ds.network_config["ethernets"]["eths"]["dhcp4"]

    def test_get_data_cloudinit_metadata_yaml(self, tmpdir):
        """
        Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is yaml.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds._get_data,
            )
            assert result
        assert "cloud-vm" == ds.metadata["instance-id"]
        assert "my-host.domain.com" == ds.metadata["local-hostname"]
        assert 2 == ds.network_config["version"]
        assert ds.network_config["ethernets"]["nics"]["dhcp4"]

    def test_get_imc_data_cloudinit_metadata_not_valid(self, caplog, tmpdir):
        """
        Test metadata is not JSON or YAML format, log a message
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds.get_data,
            )
        assert not result
        assert (
            "expected '<document start>', but found '<scalar>'" in caplog.text
        )

    def test_get_imc_data_cloudinit_metadata_not_found(self, caplog, tmpdir):
        """
        Test metadata file can't be found, log a message
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds.get_imc_data_fn,
            )
            assert result == (None, None, None)
        assert "Meta data file is not found" in caplog.text

    def test_get_data_cloudinit_userdata(self, caplog, tmpdir):
        """
        Test user data can be loaded to cloud-init user data.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
        userdata_file = os.path.join(tmpdir, "test-user")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds._get_data,
            )
            assert result
        assert "cloud-vm" == ds.metadata["instance-id"]
        assert userdata_content == ds.userdata_raw

    def test_get_imc_data_cloudinit_userdata_not_found(self, caplog, tmpdir):
        """
        Test userdata file can't be found.
        """
        paths = helpers.Paths({"cloud_dir": tmpdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = os.path.join(tmpdir, "test-cust")
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = os.path.join(tmpdir, "test-meta")
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
                    "guestcust_util.search_file": tmpdir,
                    "guestcust_util.wait_for_cust_cfg_file": conf_file,
                    "guestcust_util.get_imc_dir_path": tmpdir,
                },
                ds.get_imc_data_fn,
            )
            assert result == (None, None, None)
        assert "Userdata file is not found" in caplog.text


class TestDataSourceVMwareIMC_MarkerFiles:

    def test_false_when_markerid_none(self, tmpdir):
        """Return False when markerid provided is None."""
        assert not guestcust_util.check_marker_exists(
            markerid=None, marker_dir=tmpdir
        )

    def test_markerid_file_exist(self, tmpdir):
        """Return False when markerid file path does not exist,
        True otherwise."""
        assert not guestcust_util.check_marker_exists("123", tmpdir)
        marker_file = os.path.join(tmpdir, ".markerfile-123.txt")
        util.write_file(marker_file, "")
        assert guestcust_util.check_marker_exists("123", tmpdir)

    def test_marker_file_setup(self, tmpdir):
        """Test creation of marker files."""
        markerfilepath = os.path.join(tmpdir, ".markerfile-hi.txt")
        assert not os.path.exists(markerfilepath)
        guestcust_util.setup_marker_files(marker_id="hi", marker_dir=tmpdir)
        assert os.path.exists(markerfilepath)


def assert_metadata(ds, metadata):
    assert metadata.get("instance-id") == ds.get_instance_id()
    assert metadata.get("local-hostname") == ds.get_hostname().hostname

    expected_public_keys = metadata.get("public_keys")
    if not isinstance(expected_public_keys, list):
        expected_public_keys = [expected_public_keys]

    assert expected_public_keys == ds.get_public_ssh_keys()
    assert isinstance(ds.get_public_ssh_keys(), list)


def get_ds():
    ds = DataSourceVMware.DataSourceVMware(
        settings.CFG_BUILTIN, None, helpers.Paths({})
    )
    return ds
