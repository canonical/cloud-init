# Copyright (C) 2013 Canonical Ltd.
# Copyright 2019 Joyent, Inc.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# pylint: disable=attribute-defined-outside-init

"""This is a testcase for the SmartOS datasource.

It replicates a serial console and acts like the SmartOS console does in
order to validate return responses.

"""

import json
import multiprocessing
import os
import os.path
import re
import signal
import stat
import uuid
from binascii import crc32
from collections import namedtuple

import pytest
import serial

from cloudinit.atomic_helper import b64e
from cloudinit.event import EventScope, EventType
from cloudinit.sources import DataSourceSmartOS
from cloudinit.sources.DataSourceSmartOS import SERIAL_DEVICE, SMARTOS_ENV_KVM
from cloudinit.sources.DataSourceSmartOS import (
    convert_smartos_network_data as convert_net,
)
from cloudinit.sources.DataSourceSmartOS import (
    get_smartos_environ,
    identify_file,
)
from cloudinit.subp import ProcessExecutionError, subp, which
from cloudinit.util import write_file
from tests.unittests.helpers import mock, skipIf

DSMOS = "cloudinit.sources.DataSourceSmartOS"
SDC_NICS = json.loads(
    """
[
    {
        "nic_tag": "external",
        "primary": true,
        "mtu": 1500,
        "model": "virtio",
        "gateway": "8.12.42.1",
        "netmask": "255.255.255.0",
        "ip": "8.12.42.102",
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "gateways": [
            "8.12.42.1"
        ],
        "vlan_id": 324,
        "mac": "90:b8:d0:f5:e4:f5",
        "interface": "net0",
        "ips": [
            "8.12.42.102/24"
        ]
    },
    {
        "nic_tag": "sdc_overlay/16187209",
        "gateway": "192.168.128.1",
        "model": "virtio",
        "mac": "90:b8:d0:a5:ff:cd",
        "netmask": "255.255.252.0",
        "ip": "192.168.128.93",
        "network_uuid": "4cad71da-09bc-452b-986d-03562a03a0a9",
        "gateways": [
            "192.168.128.1"
        ],
        "vlan_id": 2,
        "mtu": 8500,
        "interface": "net1",
        "ips": [
            "192.168.128.93/22"
        ]
    }
]
"""
)


SDC_NICS_ALT = json.loads(
    """
[
    {
        "interface": "net0",
        "mac": "90:b8:d0:ae:64:51",
        "vlan_id": 324,
        "nic_tag": "external",
        "gateway": "8.12.42.1",
        "gateways": [
          "8.12.42.1"
        ],
        "netmask": "255.255.255.0",
        "ip": "8.12.42.51",
        "ips": [
          "8.12.42.51/24"
        ],
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "model": "virtio",
        "mtu": 1500,
        "primary": true
    },
    {
        "interface": "net1",
        "mac": "90:b8:d0:bd:4f:9c",
        "vlan_id": 600,
        "nic_tag": "internal",
        "netmask": "255.255.255.0",
        "ip": "10.210.1.217",
        "ips": [
          "10.210.1.217/24"
        ],
        "network_uuid": "98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
        "model": "virtio",
        "mtu": 1500
    }
]
"""
)

SDC_NICS_DHCP = json.loads(
    """
[
    {
        "interface": "net0",
        "mac": "90:b8:d0:ae:64:51",
        "vlan_id": 324,
        "nic_tag": "external",
        "gateway": "8.12.42.1",
        "gateways": [
          "8.12.42.1"
        ],
        "netmask": "255.255.255.0",
        "ip": "8.12.42.51",
        "ips": [
          "8.12.42.51/24"
        ],
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "model": "virtio",
        "mtu": 1500,
        "primary": true
    },
    {
        "interface": "net1",
        "mac": "90:b8:d0:bd:4f:9c",
        "vlan_id": 600,
        "nic_tag": "internal",
        "netmask": "255.255.255.0",
        "ip": "10.210.1.217",
        "ips": [
          "dhcp"
        ],
        "network_uuid": "98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
        "model": "virtio",
        "mtu": 1500
    }
]
"""
)

SDC_NICS_MIP = json.loads(
    """
[
    {
        "interface": "net0",
        "mac": "90:b8:d0:ae:64:51",
        "vlan_id": 324,
        "nic_tag": "external",
        "gateway": "8.12.42.1",
        "gateways": [
          "8.12.42.1"
        ],
        "netmask": "255.255.255.0",
        "ip": "8.12.42.51",
        "ips": [
          "8.12.42.51/24",
          "8.12.42.52/24"
        ],
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "model": "virtio",
        "mtu": 1500,
        "primary": true
    },
    {
        "interface": "net1",
        "mac": "90:b8:d0:bd:4f:9c",
        "vlan_id": 600,
        "nic_tag": "internal",
        "netmask": "255.255.255.0",
        "ip": "10.210.1.217",
        "ips": [
          "10.210.1.217/24",
          "10.210.1.151/24"
        ],
        "network_uuid": "98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
        "model": "virtio",
        "mtu": 1500
    }
]
"""
)

SDC_NICS_MIP_IPV6 = json.loads(
    """
[
    {
        "interface": "net0",
        "mac": "90:b8:d0:ae:64:51",
        "vlan_id": 324,
        "nic_tag": "external",
        "gateway": "8.12.42.1",
        "gateways": [
          "8.12.42.1"
        ],
        "netmask": "255.255.255.0",
        "ip": "8.12.42.51",
        "ips": [
          "2001:4800:78ff:1b:be76:4eff:fe06:96b3/64",
          "8.12.42.51/24"
        ],
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "model": "virtio",
        "mtu": 1500,
        "primary": true
    },
    {
        "interface": "net1",
        "mac": "90:b8:d0:bd:4f:9c",
        "vlan_id": 600,
        "nic_tag": "internal",
        "netmask": "255.255.255.0",
        "ip": "10.210.1.217",
        "ips": [
          "10.210.1.217/24"
        ],
        "network_uuid": "98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
        "model": "virtio",
        "mtu": 1500
    }
]
"""
)

SDC_NICS_IPV4_IPV6 = json.loads(
    """
[
    {
        "interface": "net0",
        "mac": "90:b8:d0:ae:64:51",
        "vlan_id": 324,
        "nic_tag": "external",
        "gateway": "8.12.42.1",
        "gateways": ["8.12.42.1", "2001::1", "2001::2"],
        "netmask": "255.255.255.0",
        "ip": "8.12.42.51",
        "ips": ["2001::10/64", "8.12.42.51/24", "2001::11/64",
                "8.12.42.52/32"],
        "network_uuid": "992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
        "model": "virtio",
        "mtu": 1500,
        "primary": true
    },
    {
        "interface": "net1",
        "mac": "90:b8:d0:bd:4f:9c",
        "vlan_id": 600,
        "nic_tag": "internal",
        "netmask": "255.255.255.0",
        "ip": "10.210.1.217",
        "ips": ["10.210.1.217/24"],
        "gateways": ["10.210.1.210"],
        "network_uuid": "98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
        "model": "virtio",
        "mtu": 1500
    }
]
"""
)

SDC_NICS_SINGLE_GATEWAY = json.loads(
    """
[
  {
    "interface":"net0",
    "mac":"90:b8:d0:d8:82:b4",
    "vlan_id":324,
    "nic_tag":"external",
    "gateway":"8.12.42.1",
    "gateways":["8.12.42.1"],
    "netmask":"255.255.255.0",
    "ip":"8.12.42.26",
    "ips":["8.12.42.26/24"],
    "network_uuid":"992fc7ce-6aac-4b74-aed6-7b9d2c6c0bfe",
    "model":"virtio",
    "mtu":1500,
    "primary":true
  },
  {
    "interface":"net1",
    "mac":"90:b8:d0:0a:51:31",
    "vlan_id":600,
    "nic_tag":"internal",
    "netmask":"255.255.255.0",
    "ip":"10.210.1.27",
    "ips":["10.210.1.27/24"],
    "network_uuid":"98657fdf-11f4-4ee2-88a4-ce7fe73e33a6",
    "model":"virtio",
    "mtu":1500
  }
]
"""
)

SDC_NICS_ADDRCONF = json.loads(
    """
[
        {
          "gateway": "10.64.1.129",
          "gateways": [
            "10.64.1.129"
          ],
          "interface": "net0",
          "ip": "10.64.1.130",
          "ips": [
            "10.64.1.130/26",
            "addrconf"
          ],
          "mac": "e2:7f:c1:50:eb:99",
          "model": "virtio",
          "netmask": "255.255.255.192",
          "nic_tag": "external",
          "primary": true,
          "vlan_id": 20
        }
]
"""
)

MOCK_RETURNS = {
    "hostname": "test-host",
    "root_authorized_keys": "ssh-rsa AAAAB3Nz...aC1yc2E= keyname",
    "disable_iptables_flag": None,
    "enable_motd_sys_info": None,
    "test-var1": "some data",
    "cloud-init:user-data": "\n".join(["#!/bin/sh", "/bin/true", ""]),
    "sdc:datacenter_name": "somewhere2",
    "sdc:operator-script": "\n".join(["bin/true", ""]),
    "sdc:uuid": str(uuid.uuid4()),
    "sdc:vendor-data": "\n".join(["VENDOR_DATA", ""]),
    "user-data": "\n".join(["something", ""]),
    "user-script": "\n".join(["/bin/true", ""]),
    "sdc:nics": json.dumps(SDC_NICS),
}

DMI_DATA_RETURN = "smartdc"

# Useful for calculating the length of a frame body.  A SUCCESS body will be
# followed by more characters or be one character less if SUCCESS with no
# payload.  See Section 4.3 of https://eng.joyent.com/mdata/protocol.html.
SUCCESS_LEN = len("0123abcd SUCCESS ")
NOTFOUND_LEN = len("0123abcd NOTFOUND")


class PsuedoJoyentClient:
    def __init__(self, data=None):
        if data is None:
            data = MOCK_RETURNS.copy()
        self.data = data
        self._is_open = False
        return

    def get(self, key, default=None, strip=False):
        if key in self.data:
            r = self.data[key]
            if strip:
                r = r.strip()
        else:
            r = default
        return r

    def get_json(self, key, default=None):
        result = self.get(key, default=default)
        if result is None:
            return default
        return json.loads(result)

    def exists(self):
        return True

    def open_transport(self):
        assert self._is_open is False
        self._is_open = True

    def close_transport(self):
        assert self._is_open
        self._is_open = False


@pytest.fixture
def legacy_user_d(tmp_path):
    legacy_user_dir = str(tmp_path / "legacy_user_tmp")
    os.mkdir(legacy_user_dir)
    return legacy_user_dir


@pytest.fixture
def m_jmc_client_factory(mocker):
    return mocker.patch(
        DSMOS + ".jmc_client_factory",
        return_value=PsuedoJoyentClient(MOCK_RETURNS),
    )


@pytest.fixture
def mocks(legacy_user_d, mocker, m_jmc_client_factory):
    mocker.patch(
        DSMOS + ".get_smartos_environ",
        return_value=DataSourceSmartOS.SMARTOS_ENV_KVM,
    )
    mocker.patch(
        DSMOS + ".LEGACY_USER_D",
        autospec=False,
        new=legacy_user_d,
    )
    mocker.patch(
        DSMOS + ".identify_file",
        return_value="text/plain",
    )
    mocker.patch("cloudinit.net.activators.subp.subp", return_value=("", ""))


def _get_ds(paths, ds_cfg=None):
    sys_cfg = {}
    if ds_cfg is not None:
        sys_cfg["datasource"] = {}
        sys_cfg["datasource"]["SmartOS"] = ds_cfg

    return DataSourceSmartOS.DataSourceSmartOS(
        sys_cfg, distro=None, paths=paths
    )


@pytest.fixture
def ds(paths):
    return lambda: _get_ds(paths)


@pytest.mark.usefixtures("fake_filesystem", "mocks")
class TestSmartOSDataSource:
    jmc_cfact = None
    get_smartos_environ = None

    def test_no_base64(self, paths):
        ds_cfg = {"no_base64_decode": ["test_var1"], "all_base": True}
        dsrc = _get_ds(paths, ds_cfg=ds_cfg)
        ret = dsrc.get_data()
        assert ret is True

    def test_uuid(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["sdc:uuid"] == dsrc.metadata["instance-id"]

    def test_platform_info(self, ds, m_jmc_client_factory):
        """All platform-related attributes are properly set."""
        dsrc = ds()
        assert "joyent" == dsrc.cloud_name
        assert "joyent" == dsrc.platform_type
        assert "serial (/dev/ttyS1)" == dsrc.subplatform

    def test_root_keys(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert (
            MOCK_RETURNS["root_authorized_keys"]
            == dsrc.metadata["public-keys"]
        )

    def test_hostname_b64(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["hostname"] == dsrc.metadata["local-hostname"]

    def test_hostname(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["hostname"] == dsrc.metadata["local-hostname"]

    def test_hostname_if_no_sdc_hostname(self, ds, m_jmc_client_factory):
        my_returns = MOCK_RETURNS.copy()
        my_returns["sdc:hostname"] = "sdc-" + my_returns["hostname"]
        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert my_returns["hostname"] == dsrc.metadata["local-hostname"]

    def test_sdc_hostname_if_no_hostname(self, ds, m_jmc_client_factory):
        my_returns = MOCK_RETURNS.copy()
        my_returns["sdc:hostname"] = "sdc-" + my_returns["hostname"]
        del my_returns["hostname"]
        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert my_returns["sdc:hostname"] == dsrc.metadata["local-hostname"]

    def test_sdc_uuid_if_no_hostname_or_sdc_hostname(
        self, ds, m_jmc_client_factory
    ):
        my_returns = MOCK_RETURNS.copy()
        del my_returns["hostname"]
        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert my_returns["sdc:uuid"] == dsrc.metadata["local-hostname"]

    def test_userdata(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["user-data"] == dsrc.metadata["legacy-user-data"]
        assert MOCK_RETURNS["cloud-init:user-data"] == dsrc.userdata_raw

    def test_sdc_nics(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert (
            json.loads(MOCK_RETURNS["sdc:nics"])
            == dsrc.metadata["network-data"]
        )

    def test_sdc_scripts(self, ds, legacy_user_d, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["user-script"] == dsrc.metadata["user-script"]

        legacy_script_f = "%s/user-script" % legacy_user_d
        print("legacy_script_f=%s" % legacy_script_f)
        assert os.path.exists(legacy_script_f)
        assert os.path.islink(legacy_script_f)
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        assert user_script_perm == "700"

    def test_scripts_shebanged(self, ds, legacy_user_d, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["user-script"] == dsrc.metadata["user-script"]

        legacy_script_f = "%s/user-script" % legacy_user_d
        assert os.path.exists(legacy_script_f)
        assert os.path.islink(legacy_script_f)
        shebang = None
        with open(legacy_script_f, "r") as f:
            shebang = f.readlines()[0].strip()
        assert shebang == "#!/bin/bash"
        user_script_perm = oct(os.stat(legacy_script_f)[stat.ST_MODE])[-3:]
        assert user_script_perm == "700"

    def test_scripts_shebang_not_added(
        self, ds, legacy_user_d, m_jmc_client_factory
    ):
        """
        Test that the SmartOS requirement that plain text scripts
        are executable. This test makes sure that plain texts scripts
        with out file magic have it added appropriately by cloud-init.
        """

        my_returns = MOCK_RETURNS.copy()
        my_returns["user-script"] = "\n".join(
            ["#!/usr/bin/perl", 'print("hi")', ""]
        )

        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert my_returns["user-script"] == dsrc.metadata["user-script"]

        legacy_script_f = "%s/user-script" % legacy_user_d
        assert os.path.exists(legacy_script_f)
        assert os.path.islink(legacy_script_f)
        shebang = None
        with open(legacy_script_f, "r") as f:
            shebang = f.readlines()[0].strip()
        assert shebang == "#!/usr/bin/perl"

    def test_userdata_removed(self, ds, legacy_user_d, m_jmc_client_factory):
        """
        User-data in the SmartOS world is supposed to be written to a file
        each and every boot. This tests to make sure that in the event the
        legacy user-data is removed, the existing user-data is backed-up
        and there is no /var/db/user-data left.
        """

        user_data_f = "%s/mdata-user-data" % legacy_user_d
        with open(user_data_f, "w") as f:
            f.write("PREVIOUS")

        my_returns = MOCK_RETURNS.copy()
        del my_returns["user-data"]

        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert dsrc.metadata.get("legacy-user-data") is None

        found_new = False
        for root, _dirs, files in os.walk(legacy_user_d):
            for name in files:
                name_f = os.path.join(root, name)
                permissions = oct(os.stat(name_f)[stat.ST_MODE])[-3:]
                if re.match(r".*\/mdata-user-data$", name_f):
                    found_new = True
                    print(name_f)
                    assert permissions == "400"

        assert found_new is False

    def test_vendor_data_not_default(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert MOCK_RETURNS["sdc:vendor-data"] == dsrc.metadata["vendor-data"]

    def test_default_vendor_data(self, ds, m_jmc_client_factory):
        my_returns = MOCK_RETURNS.copy()
        def_op_script = my_returns["sdc:vendor-data"]
        del my_returns["sdc:vendor-data"]
        m_jmc_client_factory.return_value = PsuedoJoyentClient(my_returns)
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert def_op_script != dsrc.metadata["vendor-data"]

        # we expect default vendor-data is a boothook
        assert dsrc.vendordata_raw.startswith("#cloud-boothook")

    def test_disable_iptables_flag(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert (
            MOCK_RETURNS["disable_iptables_flag"]
            == dsrc.metadata["iptables_disable"]
        )

    def test_motd_sys_info(self, ds, m_jmc_client_factory):
        dsrc = ds()
        ret = dsrc.get_data()
        assert ret is True
        assert (
            MOCK_RETURNS["enable_motd_sys_info"]
            == dsrc.metadata["motd_sys_info"]
        )

    def test_default_ephemeral(self, ds):
        # Test to make sure that the builtin config has the ephemeral
        # configuration.
        dsrc = ds()
        cfg = dsrc.get_config_obj()
        ret = dsrc.get_data()
        assert ret is True

        assert "disk_setup" in cfg
        assert "fs_setup" in cfg
        assert isinstance(cfg["disk_setup"], dict)
        assert isinstance(cfg["fs_setup"], list)

    def test_override_disk_aliases(self, paths):
        # Test to make sure that the built-in DS is overriden
        builtin = DataSourceSmartOS.BUILTIN_DS_CONFIG

        mydscfg = {"disk_aliases": {"FOO": "/dev/bar"}}

        # expect that these values are in builtin, or this is pointless
        for k in mydscfg:
            assert k in builtin

        dsrc = _get_ds(paths, ds_cfg=mydscfg)
        ret = dsrc.get_data()
        assert ret is True

        assert (
            mydscfg["disk_aliases"]["FOO"]
            == dsrc.ds_cfg["disk_aliases"]["FOO"]
        )

        assert (
            dsrc.device_name_to_device("FOO") == mydscfg["disk_aliases"]["FOO"]
        )

    def test_reconfig_network_on_boot(self, ds, m_jmc_client_factory):
        # Test to ensure that network is configured from metadata on each boot
        assert {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
        } == ds().default_update_events[EventScope.NETWORK]


class TestIdentifyFile:
    """Test the 'identify_file' utility."""

    @pytest.mark.allow_subp_for("file")
    @skipIf(not which("file"), "command 'file' not available.")
    def test_file_happy_path(self, tmp_path):
        """Test file is available and functional on plain text."""
        fname = str(tmp_path / "myfile")
        write_file(fname, "plain text content here\n")
        assert "text/plain" == identify_file(fname)

    @mock.patch(DSMOS + ".subp.subp")
    def test_returns_none_on_error(self, m_subp, tmp_path):
        """On 'file' execution error, None should be returned."""
        m_subp.side_effect = ProcessExecutionError("FILE_FAILED", exit_code=99)
        fname = str(tmp_path / "myfile")
        write_file(fname, "plain text content here\n")
        assert None is identify_file(fname)
        assert [
            mock.call(["file", "--brief", "--mime-type", fname])
        ] == m_subp.call_args_list


class ShortReader:
    """Implements a 'read' interface for bytes provided.
    much like io.BytesIO but the 'endbyte' acts as if EOF.
    When it is reached a short will be returned."""

    def __init__(self, initial_bytes, endbyte=b"\0"):
        self.data = initial_bytes
        self.index = 0
        self.len = len(self.data)
        self.endbyte = endbyte

    @property
    def emptied(self):
        return self.index >= self.len

    def read(self, size=-1):
        """Read size bytes but not past a null."""
        if size == 0 or self.index >= self.len:
            return b""

        rsize = size
        if size < 0 or size + self.index > self.len:
            rsize = self.len - self.index

        next_null = self.data.find(self.endbyte, self.index, rsize)
        if next_null >= 0:
            rsize = next_null - self.index + 1
        i = self.index
        self.index += rsize
        ret = self.data[i : i + rsize]
        if len(ret) and ret[-1:] == self.endbyte:
            ret = ret[:-1]
        return ret


@pytest.fixture
def m_serial(mocker):
    return mocker.MagicMock(spec=serial.Serial)


@pytest.fixture
def joyent_metadata(mocker, m_serial):
    res = namedtuple(
        "joyent",
        [
            "serial",
            "request_id",
            "metadata_value",
            "response_parts",
            "metasource_data",
            "metasource_data_len",
        ],
        defaults=(None, None, None, None, None, None),
    )

    res.serial = m_serial
    res.request_id = 0xABCDEF12
    res.metadata_value = "value"
    res.response_parts = {
        "command": "SUCCESS",
        "crc": "b5a9ff00",
        "length": SUCCESS_LEN + len(b64e(res.metadata_value)),
        "payload": b64e(res.metadata_value),
        "request_id": "{0:08x}".format(res.request_id),
    }

    def make_response():
        payloadstr = ""
        if "payload" in res.response_parts:  # pylint: disable=E1135
            payloadstr = " {0}".format(
                res.response_parts["payload"]
            )  # pylint: disable=E1136
        return (
            "V2 {length} {crc} {request_id} "
            "{command}{payloadstr}\n".format(
                payloadstr=payloadstr,
                **res.response_parts  # pylint: disable=E1134
            ).encode("ascii")
        )

    res.metasource_data = None

    def read_response(length):
        if not res.metasource_data:
            res.metasource_data = make_response()
            res.metasource_data_len = len(res.metasource_data)
        resp = res.metasource_data[:length]  # pylint: disable=E1136
        res.metasource_data = res.metasource_data[
            length:
        ]  # pylint: disable=E1136
        return resp

    res.serial.read.side_effect = read_response
    mocker.patch(
        "cloudinit.sources.DataSourceSmartOS.random.randint",
        mock.Mock(return_value=res.request_id),
    )
    return res


@pytest.fixture
def joyent_client(joyent_metadata):
    return DataSourceSmartOS.JoyentMetadataClient(
        fp=joyent_metadata.serial,
        smartos_type=DataSourceSmartOS.SMARTOS_ENV_KVM,
    )


def _get_written_line(joyent_client, m_serial, key="some_key"):
    joyent_client.get(key)
    return m_serial.write.call_args[0][0]


@pytest.fixture
def joyent_serial_client(joyent_metadata):
    joyent_metadata.serial.timeout = 1
    return DataSourceSmartOS.JoyentMetadataSerialClient(
        None, fp=joyent_metadata.serial
    )


@pytest.mark.usefixtures("fake_filesystem")
class TestJoyentMetadataClient:

    invalid = b"invalid command\n"
    failure = b"FAILURE\n"
    v2_ok = b"V2_OK\n"

    def assertEndsWith(self, haystack, prefix):
        assert haystack.endswith(prefix), "{0} does not end with '{1}'".format(
            repr(haystack), prefix
        )

    def assertStartsWith(self, haystack, prefix):
        assert haystack.startswith(
            prefix
        ), "{0} does not start with '{1}'".format(repr(haystack), prefix)

    def assertNoMoreSideEffects(self, obj):
        with pytest.raises(StopIteration):
            obj()

    def test_get_metadata_writes_a_single_line(self, m_serial, joyent_client):
        joyent_client.get("some_key")
        assert 1 == m_serial.write.call_count
        written_line = m_serial.write.call_args[0][0]
        self.assertEndsWith(
            written_line.decode("ascii"), b"\n".decode("ascii")
        )
        assert 1 == written_line.count(b"\n")

    def test_get_metadata_writes_bytes(self, joyent_client, m_serial):
        assert isinstance(_get_written_line(joyent_client, m_serial), bytes)

    def test_get_metadata_line_starts_with_v2(self, joyent_client, m_serial):
        foo = _get_written_line(joyent_client, m_serial)
        self.assertStartsWith(foo.decode("ascii"), b"V2".decode("ascii"))

    def test_get_metadata_uses_get_command(self, joyent_client, m_serial):
        parts = (
            _get_written_line(joyent_client, m_serial)
            .decode("ascii")
            .strip()
            .split(" ")
        )
        assert "GET" == parts[4]

    def test_get_metadata_base64_encodes_argument(
        self, joyent_client, m_serial
    ):
        key = "my_key"
        parts = (
            _get_written_line(joyent_client, m_serial, key)
            .decode("ascii")
            .strip()
            .split(" ")
        )
        assert b64e(key) == parts[5]

    def test_get_metadata_calculates_length_correctly(
        self, joyent_client, m_serial
    ):
        parts = (
            _get_written_line(joyent_client, m_serial)
            .decode("ascii")
            .strip()
            .split(" ")
        )
        expected_length = len(" ".join(parts[3:]))
        assert expected_length == int(parts[1])

    def test_get_metadata_uses_appropriate_request_id(
        self, joyent_client, m_serial
    ):
        parts = (
            _get_written_line(joyent_client, m_serial)
            .decode("ascii")
            .strip()
            .split(" ")
        )
        request_id = parts[3]
        assert 8 == len(request_id)
        assert request_id == request_id.lower()

    def test_get_metadata_uses_random_number_for_request_id(
        self, joyent_client, joyent_metadata, m_serial
    ):
        line = _get_written_line(joyent_client, m_serial)
        request_id = line.decode("ascii").strip().split(" ")[3]
        assert "{0:08x}".format(joyent_metadata.request_id) == request_id

    def test_get_metadata_checksums_correctly(self, joyent_client, m_serial):
        parts = (
            _get_written_line(joyent_client, m_serial)
            .decode("ascii")
            .strip()
            .split(" ")
        )
        expected_checksum = "{0:08x}".format(
            crc32(" ".join(parts[3:]).encode("utf-8")) & 0xFFFFFFFF
        )
        checksum = parts[2]
        assert expected_checksum == checksum

    def test_get_metadata_reads_a_line(
        self, joyent_client, joyent_metadata, m_serial
    ):
        joyent_client.get("some_key")
        assert joyent_metadata.metasource_data_len == m_serial.read.call_count

    def test_get_metadata_returns_valid_value(
        self, joyent_client, joyent_metadata
    ):
        value = joyent_client.get("some_key")
        assert joyent_metadata.metadata_value == value

    def test_get_metadata_throws_exception_for_incorrect_length(
        self, joyent_client, joyent_metadata
    ):
        joyent_metadata.response_parts["length"] = 0
        with pytest.raises(DataSourceSmartOS.JoyentMetadataFetchException):
            joyent_client.get(
                "some_key",
            )

    def test_get_metadata_throws_exception_for_incorrect_crc(
        self, joyent_client, joyent_metadata
    ):
        joyent_metadata.response_parts["crc"] = "deadbeef"
        with pytest.raises(DataSourceSmartOS.JoyentMetadataFetchException):
            joyent_client.get(
                "some_key",
            )

    def test_get_metadata_throws_exception_for_request_id_mismatch(
        self, joyent_client, joyent_metadata
    ):
        joyent_metadata.response_parts["request_id"] = "deadbeef"
        joyent_client._checksum = lambda _: joyent_metadata.response_parts[
            "crc"
        ]
        with pytest.raises(DataSourceSmartOS.JoyentMetadataFetchException):
            joyent_client.get("some_key")

    def test_get_metadata_returns_None_if_value_not_found(
        self, joyent_client, joyent_metadata
    ):
        joyent_metadata.response_parts["payload"] = ""
        joyent_metadata.response_parts["command"] = "NOTFOUND"
        joyent_metadata.response_parts["length"] = NOTFOUND_LEN
        joyent_client._checksum = lambda _: joyent_metadata.response_parts[
            "crc"
        ]
        assert joyent_client.get("some_key") is None

    def test_negotiate(self, joyent_client):
        reader = ShortReader(self.v2_ok)
        joyent_client.fp.read.side_effect = reader.read
        joyent_client._negotiate()
        assert reader.emptied

    def test_negotiate_short_response(self, joyent_client):
        # chopped '\n' from v2_ok.
        reader = ShortReader(self.v2_ok[:-1] + b"\0")
        joyent_client.fp.read.side_effect = reader.read
        with pytest.raises(DataSourceSmartOS.JoyentMetadataTimeoutException):
            joyent_client._negotiate()
        assert reader.emptied

    def test_negotiate_bad_response(self, joyent_client):
        reader = ShortReader(b"garbage\n" + self.v2_ok)
        joyent_client.fp.read.side_effect = reader.read
        with pytest.raises(DataSourceSmartOS.JoyentMetadataFetchException):
            joyent_client._negotiate()
        assert self.v2_ok == joyent_client.fp.read()

    def test_serial_open_transport(self, joyent_serial_client):
        reader = ShortReader(b"garbage\0" + self.invalid + self.v2_ok)
        joyent_serial_client.fp.read.side_effect = reader.read
        joyent_serial_client.open_transport()
        assert reader.emptied

    def test_flush_failure(self, joyent_serial_client):
        reader = ShortReader(
            b"garbage" + b"\0" + self.failure + self.invalid + self.v2_ok
        )
        joyent_serial_client.fp.read.side_effect = reader.read
        joyent_serial_client.open_transport()
        assert reader.emptied

    def test_flush_many_timeouts(self, joyent_serial_client):
        reader = ShortReader(b"\0" * 100 + self.invalid + self.v2_ok)
        joyent_serial_client.fp.read.side_effect = reader.read
        joyent_serial_client.open_transport()
        assert reader.emptied

    def test_list_metadata_returns_list(self, joyent_client, joyent_metadata):
        parts = ["foo", "bar"]
        value = b64e("\n".join(parts))
        joyent_metadata.response_parts["payload"] = value
        joyent_metadata.response_parts["crc"] = "40873553"
        joyent_metadata.response_parts["length"] = SUCCESS_LEN + len(value)
        assert joyent_client.list() == parts

    def test_list_metadata_returns_empty_list_if_no_customer_metadata(
        self, joyent_client, joyent_metadata
    ):
        del joyent_metadata.response_parts["payload"]
        joyent_metadata.response_parts["length"] = SUCCESS_LEN - 1
        joyent_metadata.response_parts["crc"] = "14e563ba"
        assert joyent_client.list() == []


class TestNetworkConversion:
    def test_convert_simple(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.102/24",
                        }
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:f5:e4:f5",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"type": "static", "address": "192.168.128.93/22"}
                    ],
                    "mtu": 8500,
                    "mac_address": "90:b8:d0:a5:ff:cd",
                },
            ],
        }
        found = convert_net(SDC_NICS)
        assert expected == found

    def test_convert_simple_alt(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.51/24",
                        }
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:ae:64:51",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"type": "static", "address": "10.210.1.217/24"}
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:bd:4f:9c",
                },
            ],
        }
        found = convert_net(SDC_NICS_ALT)
        assert expected == found

    def test_convert_simple_dhcp(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.51/24",
                        }
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:ae:64:51",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [{"type": "dhcp4"}],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:bd:4f:9c",
                },
            ],
        }
        found = convert_net(SDC_NICS_DHCP)
        assert expected == found

    def test_convert_simple_multi_ip(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.51/24",
                        },
                        {"type": "static", "address": "8.12.42.52/24"},
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:ae:64:51",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"type": "static", "address": "10.210.1.217/24"},
                        {"type": "static", "address": "10.210.1.151/24"},
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:bd:4f:9c",
                },
            ],
        }
        found = convert_net(SDC_NICS_MIP)
        assert expected == found

    def test_convert_with_dns(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.51/24",
                        }
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:ae:64:51",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [{"type": "dhcp4"}],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:bd:4f:9c",
                },
                {
                    "type": "nameserver",
                    "address": ["8.8.8.8", "8.8.8.1"],
                    "search": ["local"],
                },
            ],
        }
        found = convert_net(
            network_data=SDC_NICS_DHCP,
            dns_servers=["8.8.8.8", "8.8.8.1"],
            dns_domain="local",
        )
        assert expected == found

    def test_convert_simple_multi_ipv6(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "type": "static",
                            "address": (
                                "2001:4800:78ff:1b:be76:4eff:fe06:96b3/64"
                            ),
                        },
                        {
                            "type": "static",
                            "gateway": "8.12.42.1",
                            "address": "8.12.42.51/24",
                        },
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:ae:64:51",
                },
                {
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"type": "static", "address": "10.210.1.217/24"}
                    ],
                    "mtu": 1500,
                    "mac_address": "90:b8:d0:bd:4f:9c",
                },
            ],
        }
        found = convert_net(SDC_NICS_MIP_IPV6)
        assert expected == found

    def test_convert_simple_both_ipv4_ipv6(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "90:b8:d0:ae:64:51",
                    "mtu": 1500,
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "address": "2001::10/64",
                            "gateway": "2001::1",
                            "type": "static",
                        },
                        {
                            "address": "8.12.42.51/24",
                            "gateway": "8.12.42.1",
                            "type": "static",
                        },
                        {"address": "2001::11/64", "type": "static"},
                        {"address": "8.12.42.52/32", "type": "static"},
                    ],
                },
                {
                    "mac_address": "90:b8:d0:bd:4f:9c",
                    "mtu": 1500,
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"address": "10.210.1.217/24", "type": "static"}
                    ],
                },
            ],
        }
        found = convert_net(SDC_NICS_IPV4_IPV6)
        assert expected == found

    def test_gateways_not_on_all_nics(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "90:b8:d0:d8:82:b4",
                    "mtu": 1500,
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "address": "8.12.42.26/24",
                            "gateway": "8.12.42.1",
                            "type": "static",
                        }
                    ],
                },
                {
                    "mac_address": "90:b8:d0:0a:51:31",
                    "mtu": 1500,
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {"address": "10.210.1.27/24", "type": "static"}
                    ],
                },
            ],
        }
        found = convert_net(SDC_NICS_SINGLE_GATEWAY)
        assert expected == found

    def test_routes_on_all_nics(self):
        routes = [
            {"linklocal": False, "dst": "3.0.0.0/8", "gateway": "8.12.42.3"},
            {"linklocal": False, "dst": "4.0.0.0/8", "gateway": "10.210.1.4"},
        ]
        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "90:b8:d0:d8:82:b4",
                    "mtu": 1500,
                    "name": "net0",
                    "type": "physical",
                    "subnets": [
                        {
                            "address": "8.12.42.26/24",
                            "gateway": "8.12.42.1",
                            "type": "static",
                            "routes": [
                                {
                                    "network": "3.0.0.0/8",
                                    "gateway": "8.12.42.3",
                                },
                                {
                                    "network": "4.0.0.0/8",
                                    "gateway": "10.210.1.4",
                                },
                            ],
                        }
                    ],
                },
                {
                    "mac_address": "90:b8:d0:0a:51:31",
                    "mtu": 1500,
                    "name": "net1",
                    "type": "physical",
                    "subnets": [
                        {
                            "address": "10.210.1.27/24",
                            "type": "static",
                            "routes": [
                                {
                                    "network": "3.0.0.0/8",
                                    "gateway": "8.12.42.3",
                                },
                                {
                                    "network": "4.0.0.0/8",
                                    "gateway": "10.210.1.4",
                                },
                            ],
                        }
                    ],
                },
            ],
        }
        found = convert_net(SDC_NICS_SINGLE_GATEWAY, routes=routes)
        self.maxDiff = None
        assert expected == found

    def test_ipv6_addrconf(self):
        expected = {
            "config": [
                {
                    "mac_address": "e2:7f:c1:50:eb:99",
                    "name": "net0",
                    "subnets": [
                        {
                            "address": "10.64.1.130/26",
                            "gateway": "10.64.1.129",
                            "type": "static",
                        },
                        {"type": "dhcp6"},
                    ],
                    "type": "physical",
                }
            ],
            "version": 1,
        }
        found = convert_net(SDC_NICS_ADDRCONF)
        self.maxDiff = None
        assert expected == found


@pytest.mark.allow_subp_for("mdata-get")
@pytest.fixture
def mdata_proc():
    mdata_proc = multiprocessing.Process(target=start_mdata_loop)
    mdata_proc.start()

    yield mdata_proc

    # os.kill() rather than mdata_proc.terminate() to avoid console spam.
    os.kill(mdata_proc.pid, signal.SIGKILL)
    mdata_proc.join()


def start_mdata_loop():
    """
    The mdata-get command is repeatedly run in a separate process so
    that it may try to race with metadata operations performed in the
    main test process.  Use of mdata-get is better than two processes
    using the protocol implementation in DataSourceSmartOS because we
    are testing to be sure that cloud-init and mdata-get respect each
    others locks.
    """
    rcs = list(range(256))
    while True:
        subp(["mdata-get", "sdc:routes"], rcs=rcs)


@pytest.mark.skipif(
    get_smartos_environ() != SMARTOS_ENV_KVM,
    reason="Only supported on KVM and bhyve guests under SmartOS",
)
@pytest.mark.skipif(
    not os.access(SERIAL_DEVICE, os.W_OK),
    reason="Requires write access to " + SERIAL_DEVICE,
)
class TestSerialConcurrency:
    """
    This class tests locking on an actual serial port, and as such can only
    be run in a kvm or bhyve guest running on a SmartOS host.  A test run on
    a metadata socket will not be valid because a metadata socket ensures
    there is only one session over a connection.  In contrast, in the
    absence of proper locking multiple processes opening the same serial
    port can corrupt each others' exchanges with the metadata server.

    This takes on the order of 2 to 3 minutes to run.
    """

    @pytest.mark.allow_subp_for("mdata-get")
    def test_all_keys(self, mdata_proc):
        assert mdata_proc.pid is not None
        ds = DataSourceSmartOS
        keys = [tup[0] for tup in ds.SMARTOS_ATTRIB_MAP.values()]
        keys.extend(ds.SMARTOS_ATTRIB_JSON.values())

        client = ds.jmc_client_factory(smartos_type=SMARTOS_ENV_KVM)
        assert client is not None

        # The behavior that we are testing for was observed mdata-get running
        # 10 times at roughly the same time as cloud-init fetched each key
        # once.  cloud-init would regularly see failures before making it
        # through all keys once.
        for _ in range(3):
            for key in keys:
                # We don't care about the return value, just that it doesn't
                # thrown any exceptions.
                client.get(key)

        assert mdata_proc.exitcode is None
