# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import copy
import errno
import ipaddress
import os
from pathlib import Path
from typing import Optional
from unittest import mock

import pytest
import requests
import responses

import cloudinit.net as net
from cloudinit import subp
from cloudinit.net.ephemeral import EphemeralIPv4Network, EphemeralIPv6Network
from cloudinit.subp import ProcessExecutionError
from cloudinit.util import ensure_file, write_file
from tests.unittests.helpers import (
    CiTestCase,
    ResponsesTestCase,
    example_netdev,
    random_string,
)
from tests.unittests.util import MockDistro


class TestSysDevPath:
    def test_sys_dev_path(self):
        """sys_dev_path returns a path under SYS_CLASS_NET for a device."""
        dev = "something"
        path = "attribute"
        expected = net.get_sys_class_path() + dev + "/" + path
        assert expected == net.sys_dev_path(dev, path)

    def test_sys_dev_path_without_path(self):
        """When path param isn't provided it defaults to empty string."""
        dev = "something"
        expected = net.get_sys_class_path() + dev + "/"
        assert expected == net.sys_dev_path(dev)


class TestReadSysNet:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        # We mock invididual numbered tmpdirs here because these tests write
        # to the sysfs directory and stale test artifacts break later tests.
        mock_sysfs = f"{tmpdir_factory.mktemp('sysfs', numbered=True)}/"
        with mock.patch(
            "cloudinit.net.get_sys_class_path", return_value=mock_sysfs
        ):
            self.sysdir = mock_sysfs
            yield

    def test_read_sys_net_strips_contents_of_sys_path(self):
        """read_sys_net strips whitespace from the contents of a sys file."""
        content = "some stuff with trailing whitespace\t\r\n"
        write_file(os.path.join(self.sysdir, "dev", "attr"), content)
        assert content.strip() == net.read_sys_net("dev", "attr")

    def test_read_sys_net_reraises_oserror(self):
        """read_sys_net raises OSError/IOError when file doesn't exist."""
        # Non-specific Exception because versions of python OSError vs IOError.
        with pytest.raises(Exception, match="No such file or directory"):
            net.read_sys_net("dev", "attr")

    def test_read_sys_net_handles_error_with_on_enoent(self):
        """read_sys_net handles OSError/IOError with on_enoent if provided."""
        handled_errors = []

        def on_enoent(e):
            handled_errors.append(e)

        net.read_sys_net("dev", "attr", on_enoent=on_enoent)
        error = handled_errors[0]
        assert isinstance(error, Exception)
        assert "No such file or directory" in str(error)

    def test_read_sys_net_translates_content(self):
        """read_sys_net translates content when translate dict is provided."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, "dev", "attr"), content)
        translate = {"you're welcome": "de nada"}
        assert "de nada" == net.read_sys_net(
            "dev", "attr", translate=translate
        )

    def test_read_sys_net_errors_on_translation_failures(self, caplog):
        """read_sys_net raises a KeyError and logs details on failure."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, "dev", "attr"), content)
        with pytest.raises(KeyError, match='"you\'re welcome"'):
            net.read_sys_net("dev", "attr", translate={})
        assert (
            "Found unexpected (not translatable) value 'you're welcome' in "
            "'{0}dev/attr".format(self.sysdir) in caplog.text
        )

    def test_read_sys_net_handles_handles_with_onkeyerror(self):
        """read_sys_net handles translation errors calling on_keyerror."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, "dev", "attr"), content)
        handled_errors = []

        def on_keyerror(e):
            handled_errors.append(e)

        net.read_sys_net("dev", "attr", translate={}, on_keyerror=on_keyerror)
        error = handled_errors[0]
        assert isinstance(error, KeyError)
        assert '"you\'re welcome"' == str(error)

    def test_read_sys_net_safe_false_on_translate_failure(self):
        """read_sys_net_safe returns False on translation failures."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, "dev", "attr"), content)
        assert not net.read_sys_net_safe("dev", "attr", translate={})

    def test_read_sys_net_safe_returns_false_on_noent_failure(self):
        """read_sys_net_safe returns False on file not found failures."""
        assert not net.read_sys_net_safe("dev", "attr")

    def test_read_sys_net_int_returns_none_on_error(self):
        """read_sys_net_safe returns None on failures."""
        assert not net.read_sys_net_int("dev", "attr")

    def test_read_sys_net_int_returns_none_on_valueerror(self):
        """read_sys_net_safe returns None when content is not an int."""
        write_file(os.path.join(self.sysdir, "dev", "attr"), "NOTINT\n")
        assert not net.read_sys_net_int("dev", "attr")

    def test_read_sys_net_int_returns_integer_from_content(self):
        """read_sys_net_safe returns None on failures."""
        write_file(os.path.join(self.sysdir, "dev", "attr"), "1\n")
        assert 1 == net.read_sys_net_int("dev", "attr")

    def test_is_up_true(self):
        """is_up is True if sys/net/devname/operstate is 'up' or 'unknown'."""
        for state in ["up", "unknown"]:
            write_file(os.path.join(self.sysdir, "eth0", "operstate"), state)
            assert net.is_up("eth0")

    def test_is_up_false(self):
        """is_up is False if sys/net/devname/operstate is 'down' or invalid."""
        for state in ["down", "incomprehensible"]:
            write_file(os.path.join(self.sysdir, "eth0", "operstate"), state)
            assert not net.is_up("eth0")

    def test_is_bridge(self):
        """is_bridge is True when /sys/net/devname/bridge exists."""
        assert not net.is_bridge("eth0")
        ensure_file(os.path.join(self.sysdir, "eth0", "bridge"))
        assert net.is_bridge("eth0")

    def test_is_bond(self):
        """is_bond is True when /sys/net/devname/bonding exists."""
        assert not net.is_bond("eth0")
        ensure_file(os.path.join(self.sysdir, "eth0", "bonding"))
        assert net.is_bond("eth0")

    def test_get_master(self):
        """get_master returns the path when /sys/net/devname/master exists."""
        assert net.get_master("enP1s1") is None
        master_path = os.path.join(self.sysdir, "enP1s1", "master")
        ensure_file(master_path)
        assert master_path == net.get_master("enP1s1")

    def test_master_is_bridge_or_bond(self):
        bridge_mac = "aa:bb:cc:aa:bb:cc"
        bond_mac = "cc:bb:aa:cc:bb:aa"

        # No master => False
        write_file(os.path.join(self.sysdir, "eth1", "address"), bridge_mac)
        write_file(os.path.join(self.sysdir, "eth2", "address"), bond_mac)

        assert not net.master_is_bridge_or_bond("eth1")
        assert not net.master_is_bridge_or_bond("eth2")

        # masters without bridge/bonding => False
        write_file(os.path.join(self.sysdir, "br0", "address"), bridge_mac)
        write_file(os.path.join(self.sysdir, "bond0", "address"), bond_mac)

        os.symlink("../br0", os.path.join(self.sysdir, "eth1", "master"))
        os.symlink("../bond0", os.path.join(self.sysdir, "eth2", "master"))

        assert not net.master_is_bridge_or_bond("eth1")
        assert not net.master_is_bridge_or_bond("eth2")

        # masters with bridge/bonding => True
        write_file(os.path.join(self.sysdir, "br0", "bridge"), "")
        write_file(os.path.join(self.sysdir, "bond0", "bonding"), "")

        assert net.master_is_bridge_or_bond("eth1")
        assert net.master_is_bridge_or_bond("eth2")

    def test_master_is_openvswitch(self):
        ovs_mac = "bb:cc:aa:bb:cc:aa"

        # No master => False
        write_file(os.path.join(self.sysdir, "eth1", "address"), ovs_mac)

        assert not net.master_is_bridge_or_bond("eth1")

        # masters without ovs-system => False
        write_file(os.path.join(self.sysdir, "ovs-system", "address"), ovs_mac)

        os.symlink(
            "../ovs-system", os.path.join(self.sysdir, "eth1", "master")
        )

        assert not net.master_is_openvswitch("eth1")

        # masters with ovs-system => True
        os.symlink(
            "../ovs-system",
            os.path.join(self.sysdir, "eth1", "upper_ovs-system"),
        )

        assert net.master_is_openvswitch("eth1")

    def test_is_vlan(self):
        """is_vlan is True when /sys/net/devname/uevent has DEVTYPE=vlan."""
        ensure_file(os.path.join(self.sysdir, "eth0", "uevent"))
        assert not net.is_vlan("eth0")
        content = "junk\nDEVTYPE=vlan\njunk\n"
        write_file(os.path.join(self.sysdir, "eth0", "uevent"), content)
        assert net.is_vlan("eth0")


class TestGenerateFallbackConfig(CiTestCase):
    def setUp(self):
        super(TestGenerateFallbackConfig, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)
        self.add_patch(
            "cloudinit.net.util.is_container",
            "m_is_container",
            return_value=False,
        )
        self.add_patch("cloudinit.net.util.udevadm_settle", "m_settle")
        self.add_patch(
            "cloudinit.net.is_netfailover", "m_netfail", return_value=False
        )
        self.add_patch(
            "cloudinit.net.is_netfail_master",
            "m_netfail_master",
            return_value=False,
        )

    def test_generate_fallback_finds_connected_eth_with_mac(self):
        """generate_fallback_config finds any connected device with a mac."""
        write_file(os.path.join(self.sysdir, "eth0", "carrier"), "1")
        write_file(os.path.join(self.sysdir, "eth1", "carrier"), "1")
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth1", "address"), mac)
        expected = {
            "ethernets": {
                "eth1": {
                    "match": {"macaddress": mac},
                    "dhcp4": True,
                    "dhcp6": True,
                    "set-name": "eth1",
                }
            },
            "version": 2,
        }
        self.assertEqual(expected, net.generate_fallback_config())

    def test_generate_fallback_finds_dormant_eth_with_mac(self):
        """generate_fallback_config finds any dormant device with a mac."""
        write_file(os.path.join(self.sysdir, "eth0", "dormant"), "1")
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth0", "address"), mac)
        expected = {
            "ethernets": {
                "eth0": {
                    "match": {"macaddress": mac},
                    "dhcp4": True,
                    "dhcp6": True,
                    "set-name": "eth0",
                }
            },
            "version": 2,
        }
        self.assertEqual(expected, net.generate_fallback_config())

    def test_generate_fallback_finds_eth_by_operstate(self):
        """generate_fallback_config finds any dormant device with a mac."""
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth0", "address"), mac)
        expected = {
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "dhcp6": True,
                    "match": {"macaddress": mac},
                    "set-name": "eth0",
                }
            },
            "version": 2,
        }
        valid_operstates = ["dormant", "down", "lowerlayerdown", "unknown"]
        for state in valid_operstates:
            write_file(os.path.join(self.sysdir, "eth0", "operstate"), state)
            self.assertEqual(expected, net.generate_fallback_config())
        write_file(os.path.join(self.sysdir, "eth0", "operstate"), "noworky")
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_veth(self):
        """generate_fallback_config will skip any veth interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, "veth0", "carrier"), "1")
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_bridges(self):
        """generate_fallback_config will skip any bridges interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, "eth0", "carrier"), "1")
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth0", "address"), mac)
        ensure_file(os.path.join(self.sysdir, "eth0", "bridge"))
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_bonds(self):
        """generate_fallback_config will skip any bonded interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, "eth0", "carrier"), "1")
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth0", "address"), mac)
        ensure_file(os.path.join(self.sysdir, "eth0", "bonding"))
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_netfail_devs(self):
        """gen_fallback_config ignores netfail primary,sby no mac on master."""
        mac = "aa:bb:cc:aa:bb:cc"  # netfailover devs share the same mac
        for iface in ["ens3", "ens3sby", "enP0s1f3"]:
            write_file(os.path.join(self.sysdir, iface, "carrier"), "1")
            write_file(
                os.path.join(self.sysdir, iface, "addr_assign_type"), "0"
            )
            write_file(os.path.join(self.sysdir, iface, "address"), mac)

        def is_netfail(iface, _driver=None):
            # ens3 is the master
            if iface == "ens3":
                return False
            return True

        self.m_netfail.side_effect = is_netfail

        def is_netfail_master(iface, _driver=None):
            # ens3 is the master
            if iface == "ens3":
                return True
            return False

        self.m_netfail_master.side_effect = is_netfail_master
        expected = {
            "ethernets": {
                "ens3": {
                    "dhcp4": True,
                    "dhcp6": True,
                    "match": {"name": "ens3"},
                    "set-name": "ens3",
                }
            },
            "version": 2,
        }
        result = net.generate_fallback_config()
        self.assertEqual(expected, result)


class TestNetFindFallBackNic(CiTestCase):
    def setUp(self):
        super(TestNetFindFallBackNic, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)
        self.add_patch(
            "cloudinit.net.util.is_container",
            "m_is_container",
            return_value=False,
        )
        self.add_patch("cloudinit.net.util.udevadm_settle", "m_settle")

    def test_generate_fallback_finds_first_connected_eth_with_mac(self):
        """find_fallback_nic finds any connected device with a mac."""
        write_file(os.path.join(self.sysdir, "eth0", "carrier"), "1")
        write_file(os.path.join(self.sysdir, "eth1", "carrier"), "1")
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth1", "address"), mac)
        self.assertEqual("eth1", net.find_fallback_nic())


class TestNetFindCandidateNics:
    def create_fake_interface(
        self,
        name: str,
        address: Optional[str] = "aa:bb:cc:aa:bb:cc",
        carrier: bool = True,
        bonding: bool = False,
        dormant: bool = False,
        driver: str = "fakenic",
        bridge: bool = False,
        failover_standby: bool = False,
        operstate: Optional[str] = None,
    ):
        interface_path = self.sys_path / name
        interface_path.mkdir(parents=True)

        if address is not None:
            (interface_path / "address").write_text(str(address))

        if carrier:
            (interface_path / "carrier").write_text("1")
        else:
            (interface_path / "carrier").write_text("0")

        if bonding:
            (interface_path / "bonding").write_text("1")

        if bridge:
            (interface_path / "bridge").write_text("1")

        if dormant:
            (interface_path / "dormant").write_text("1")
        else:
            (interface_path / "dormant").write_text("0")

        if operstate:
            (interface_path / "operstate").write_text(operstate)

        device_path = interface_path / "device"
        device_path.mkdir()
        if failover_standby:
            driver = "virtio_net"
            (interface_path / "master").symlink_to(os.path.join("..", name))
            (device_path / "features").write_text("1" * 64)

        if driver:
            (device_path / driver).write_text(driver)
            (device_path / "driver").symlink_to(driver)

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmpdir):
        self.sys_path = Path(tmpdir) / "sys"
        monkeypatch.setattr(
            net, "get_sys_class_path", lambda: str(self.sys_path) + "/"
        )
        monkeypatch.setattr(
            net.util,
            "is_container",
            lambda: False,
        )
        monkeypatch.setattr(net.util, "udevadm_settle", lambda: None)

    def test_ignored_interfaces(self):
        self.create_fake_interface(
            name="ethNoCarrierDormantOperstateIgnored",
            carrier=False,
        )
        self.create_fake_interface(
            name="ethWithoutMacIgnored",
            address=None,
        )
        self.create_fake_interface(name="vethIgnored", carrier=1)
        self.create_fake_interface(
            name="bondIgnored",
            bonding=True,
        )
        self.create_fake_interface(
            name="bridgeIgnored",
            bridge=True,
        )
        self.create_fake_interface(
            name="failOverIgnored",
            failover_standby=True,
        )
        self.create_fake_interface(
            name="TestingOperStateIgnored",
            carrier=False,
            operstate="testing",
        )
        self.create_fake_interface(
            name="hv",
            driver="hv_netvsc",
            address="00:11:22:00:00:f0",
        )
        self.create_fake_interface(
            name="hv_vf_mlx4",
            driver="mlx4_core",
            address="00:11:22:00:00:f0",
        )
        self.create_fake_interface(
            name="hv_vf_mlx5",
            driver="mlx5_core",
            address="00:11:22:00:00:f0",
        )
        self.create_fake_interface(
            name="hv_vf_mana",
            driver="mana",
            address="00:11:22:00:00:f0",
        )

        assert net.find_candidate_nics_on_linux() == ["hv"]

    def test_carrier_preferred(self):
        self.create_fake_interface(name="eth0", carrier=False, dormant=True)
        self.create_fake_interface(name="eth1")

        assert net.find_candidate_nics_on_linux() == ["eth1", "eth0"]

    def test_natural_sort(self):
        self.create_fake_interface(name="a")
        self.create_fake_interface(name="a1")
        self.create_fake_interface(name="a2")
        self.create_fake_interface(name="a10")
        self.create_fake_interface(name="b1")

        assert net.find_candidate_nics_on_linux() == [
            "a",
            "a1",
            "a2",
            "a10",
            "b1",
        ]

    def test_eth0_preferred_with_carrier(self):
        self.create_fake_interface(name="abc0")
        self.create_fake_interface(name="eth0")

        assert net.find_candidate_nics_on_linux() == ["eth0", "abc0"]

    @pytest.mark.parametrize("dormant", [False, True])
    @pytest.mark.parametrize(
        "operstate", ["dormant", "down", "lowerlayerdown", "unknown"]
    )
    def test_eth0_preferred_after_carrier(self, dormant, operstate):
        self.create_fake_interface(name="xeth10")
        self.create_fake_interface(name="eth", carrier=False, dormant=True)
        self.create_fake_interface(
            name="eth0",
            carrier=False,
            dormant=dormant,
            operstate=operstate,
        )
        self.create_fake_interface(name="eth1", carrier=False, dormant=True)
        self.create_fake_interface(
            name="eth2",
            carrier=False,
            operstate=operstate,
        )

        assert net.find_candidate_nics_on_linux() == [
            "xeth10",
            "eth0",
            "eth",
            "eth1",
            "eth2",
        ]

    def test_no_nics(self):
        assert net.find_candidate_nics_on_linux() == []


class TestGetDeviceList(CiTestCase):
    def setUp(self):
        super(TestGetDeviceList, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_get_devicelist_raise_oserror(self):
        """get_devicelist raise any non-ENOENT OSerror."""
        error = OSError("Can not do it")
        error.errno = errno.EPERM  # Set non-ENOENT
        self.m_sys_path.side_effect = error
        with self.assertRaises(OSError) as context_manager:
            net.get_devicelist()
        exception = context_manager.exception
        self.assertEqual("Can not do it", str(exception))

    def test_get_devicelist_empty_without_sys_net(self):
        """get_devicelist returns empty list when missing SYS_CLASS_NET."""
        self.m_sys_path.return_value = "idontexist"
        self.assertEqual([], net.get_devicelist())

    def test_get_devicelist_empty_with_no_devices_in_sys_net(self):
        """get_devicelist returns empty directoty listing for SYS_CLASS_NET."""
        self.assertEqual([], net.get_devicelist())

    def test_get_devicelist_lists_any_subdirectories_in_sys_net(self):
        """get_devicelist returns a directory listing for SYS_CLASS_NET."""
        write_file(os.path.join(self.sysdir, "eth0", "operstate"), "up")
        write_file(os.path.join(self.sysdir, "eth1", "operstate"), "up")
        self.assertCountEqual(["eth0", "eth1"], net.get_devicelist())


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestGetInterfaceMAC(CiTestCase):
    def setUp(self):
        super(TestGetInterfaceMAC, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_get_interface_mac_false_with_no_mac(self):
        """get_device_list returns False when no mac is reported."""
        ensure_file(os.path.join(self.sysdir, "eth0", "bonding"))
        mac_path = os.path.join(self.sysdir, "eth0", "address")
        self.assertFalse(os.path.exists(mac_path))
        self.assertFalse(net.get_interface_mac("eth0"))

    def test_get_interface_mac(self):
        """get_interfaces returns the mac from SYS_CLASS_NET/dev/address."""
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth1", "address"), mac)
        self.assertEqual(mac, net.get_interface_mac("eth1"))

    def test_get_interface_mac_grabs_bonding_address(self):
        """get_interfaces returns the source device mac for bonded devices."""
        source_dev_mac = "aa:bb:cc:aa:bb:cc"
        bonded_mac = "dd:ee:ff:dd:ee:ff"
        write_file(os.path.join(self.sysdir, "eth1", "address"), bonded_mac)
        write_file(
            os.path.join(self.sysdir, "eth1", "bonding_slave", "perm_hwaddr"),
            source_dev_mac,
        )
        self.assertEqual(source_dev_mac, net.get_interface_mac("eth1"))

    def test_get_interfaces_empty_list_without_sys_net(self):
        """get_interfaces returns an empty list when missing SYS_CLASS_NET."""
        self.m_sys_path.return_value = "idontexist"
        self.assertEqual([], net.get_interfaces())

    def test_get_interfaces_by_mac_skips_empty_mac(self):
        """Ignore 00:00:00:00:00:00 addresses from get_interfaces_by_mac."""
        empty_mac = "00:00:00:00:00:00"
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth1", "address"), empty_mac)
        write_file(os.path.join(self.sysdir, "eth1", "addr_assign_type"), "0")
        write_file(os.path.join(self.sysdir, "eth2", "addr_assign_type"), "0")
        write_file(os.path.join(self.sysdir, "eth2", "address"), mac)
        expected = [("eth2", "aa:bb:cc:aa:bb:cc", None, None)]
        self.assertEqual(expected, net.get_interfaces())

    def test_get_interfaces_by_mac_skips_missing_mac(self):
        """Ignore interfaces without an address from get_interfaces_by_mac."""
        write_file(os.path.join(self.sysdir, "eth1", "addr_assign_type"), "0")
        address_path = os.path.join(self.sysdir, "eth1", "address")
        self.assertFalse(os.path.exists(address_path))
        mac = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth2", "addr_assign_type"), "0")
        write_file(os.path.join(self.sysdir, "eth2", "address"), mac)
        expected = [("eth2", "aa:bb:cc:aa:bb:cc", None, None)]
        self.assertEqual(expected, net.get_interfaces())

    def test_get_interfaces_by_mac_skips_master_devs(self):
        """Ignore interfaces with a master device which would have dup mac."""
        mac1 = mac2 = "aa:bb:cc:aa:bb:cc"
        write_file(os.path.join(self.sysdir, "eth1", "addr_assign_type"), "0")
        write_file(os.path.join(self.sysdir, "eth1", "address"), mac1)
        write_file(os.path.join(self.sysdir, "eth1", "master"), "blah")
        write_file(os.path.join(self.sysdir, "eth2", "addr_assign_type"), "0")
        write_file(os.path.join(self.sysdir, "eth2", "address"), mac2)
        expected = [("eth2", mac2, None, None)]
        self.assertEqual(expected, net.get_interfaces())

    @mock.patch("cloudinit.net.is_netfailover")
    def test_get_interfaces_by_mac_skips_netfailvoer(self, m_netfail):
        """Ignore interfaces if netfailover primary or standby."""
        mac = "aa:bb:cc:aa:bb:cc"  # netfailover devs share the same mac
        for iface in ["ens3", "ens3sby", "enP0s1f3"]:
            write_file(
                os.path.join(self.sysdir, iface, "addr_assign_type"), "0"
            )
            write_file(os.path.join(self.sysdir, iface, "address"), mac)

        def is_netfail(iface, _driver=None):
            # ens3 is the master
            if iface == "ens3":
                return False
            else:
                return True

        m_netfail.side_effect = is_netfail
        expected = [("ens3", mac, None, None)]
        self.assertEqual(expected, net.get_interfaces())

    def test_get_interfaces_does_not_skip_phys_members_of_bridges_and_bonds(
        self,
    ):
        bridge_mac = "aa:bb:cc:aa:bb:cc"
        bond_mac = "cc:bb:aa:cc:bb:aa"
        ovs_mac = "bb:cc:aa:bb:cc:aa"

        write_file(os.path.join(self.sysdir, "br0", "address"), bridge_mac)
        write_file(os.path.join(self.sysdir, "br0", "bridge"), "")

        write_file(os.path.join(self.sysdir, "bond0", "address"), bond_mac)
        write_file(os.path.join(self.sysdir, "bond0", "bonding"), "")

        write_file(os.path.join(self.sysdir, "ovs-system", "address"), ovs_mac)

        write_file(os.path.join(self.sysdir, "eth1", "address"), bridge_mac)
        os.symlink("../br0", os.path.join(self.sysdir, "eth1", "master"))

        write_file(os.path.join(self.sysdir, "eth2", "address"), bond_mac)
        os.symlink("../bond0", os.path.join(self.sysdir, "eth2", "master"))

        write_file(os.path.join(self.sysdir, "eth3", "address"), ovs_mac)
        os.symlink(
            "../ovs-system", os.path.join(self.sysdir, "eth3", "master")
        )
        os.symlink(
            "../ovs-system",
            os.path.join(self.sysdir, "eth3", "upper_ovs-system"),
        )

        interface_names = [interface[0] for interface in net.get_interfaces()]
        self.assertEqual(
            ["eth1", "eth2", "eth3", "ovs-system"], sorted(interface_names)
        )


class TestInterfaceHasOwnMAC(CiTestCase):
    def setUp(self):
        super(TestInterfaceHasOwnMAC, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_interface_has_own_mac_false_when_stolen(self):
        """Return False from interface_has_own_mac when address is stolen."""
        write_file(os.path.join(self.sysdir, "eth1", "addr_assign_type"), "2")
        self.assertFalse(net.interface_has_own_mac("eth1"))

    def test_interface_has_own_mac_true_when_not_stolen(self):
        """Return False from interface_has_own_mac when mac isn't stolen."""
        valid_assign_types = ["0", "1", "3"]
        assign_path = os.path.join(self.sysdir, "eth1", "addr_assign_type")
        for _type in valid_assign_types:
            write_file(assign_path, _type)
            self.assertTrue(net.interface_has_own_mac("eth1"))

    def test_interface_has_own_mac_strict_errors_on_absent_assign_type(self):
        """When addr_assign_type is absent, interface_has_own_mac errors."""
        with self.assertRaises(ValueError):
            net.interface_has_own_mac("eth1", strict=True)


@mock.patch("cloudinit.net.subp.subp")
@pytest.mark.usefixtures("disable_netdev_info")
class TestEphemeralIPV4Network(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestEphemeralIPV4Network, self).setUp()
        sys_mock = mock.patch("cloudinit.net.get_sys_class_path")
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + "/"
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_ephemeral_ipv4_network_errors_on_missing_params(self, m_subp):
        """No required params for EphemeralIPv4Network can be None."""
        required_params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
        }
        for key in required_params.keys():
            params = copy.deepcopy(required_params)
            params[key] = None
            with self.assertRaises(ValueError) as context_manager:
                EphemeralIPv4Network(
                    MockDistro(),
                    interface_addrs_before_dhcp=example_netdev,
                    **params,
                )
            error = context_manager.exception
            self.assertIn("Cannot init network on", str(error))
            self.assertEqual(0, m_subp.call_count)

    def test_ephemeral_ipv4_network_errors_invalid_mask_prefix(self, m_subp):
        """Raise an error when prefix_or_mask is not a netmask or prefix."""
        params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "broadcast": "192.168.2.255",
            "interface_addrs_before_dhcp": example_netdev,
        }
        invalid_masks = ("invalid", "invalid.", "123.123.123")
        for error_val in invalid_masks:
            params["prefix_or_mask"] = error_val
            with self.assertRaises(ValueError) as context_manager:
                with EphemeralIPv4Network(MockDistro(), **params):
                    pass
            error = context_manager.exception
            self.assertIn(
                "Cannot setup network, invalid prefix or netmask: ", str(error)
            )
            self.assertEqual(0, m_subp.call_count)

    def test_ephemeral_ipv4_network_performs_teardown(self, m_subp):
        """EphemeralIPv4Network performs teardown on the device if setup."""
        expected_setup_calls = [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "add",
                    "192.168.2.2/24",
                    "broadcast",
                    "192.168.2.255",
                    "dev",
                    "eth0",
                ],
                update_env={"LANG": "C"},
            ),
        ]
        expected_teardown_calls = [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "del",
                    "192.168.2.2/24",
                    "dev",
                    "eth0",
                ],
            ),
        ]
        params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
            "interface_addrs_before_dhcp": example_netdev,
        }
        with EphemeralIPv4Network(MockDistro(), **params):
            self.assertEqual(expected_setup_calls, m_subp.call_args_list)
        m_subp.assert_has_calls(expected_teardown_calls)

    def test_teardown_on_enter_exception(self, m_subp):
        """Ensure ephemeral teardown happens.

        Even though we're using a context manager, we need to handle any
        exceptions raised in __enter__ manually and do the appropriate
        teardown.
        """

        def side_effect(args, **kwargs):
            if "append" in args and "3.3.3.3/32" in args:
                raise subp.ProcessExecutionError("oh no!")

        m_subp.side_effect = side_effect

        with pytest.raises(subp.ProcessExecutionError):
            with EphemeralIPv4Network(
                MockDistro(),
                interface="eth0",
                ip="1.1.1.1",
                prefix_or_mask="255.255.255.0",
                broadcast="1.1.1.255",
                interface_addrs_before_dhcp=example_netdev,
                static_routes=[
                    ("2.2.2.2/32", "9.9.9.9"),
                    ("3.3.3.3/32", "8.8.8.8"),
                ],
            ):
                pass

        expected_teardown_calls = [
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "del",
                    "2.2.2.2/32",
                    "via",
                    "9.9.9.9",
                    "dev",
                    "eth0",
                ],
            ),
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "del",
                    "1.1.1.1/24",
                    "dev",
                    "eth0",
                ],
            ),
        ]
        for teardown in expected_teardown_calls:
            assert teardown in m_subp.call_args_list

    def test_ephemeral_ipv4_network_noop_when_configured(self, m_subp):
        """EphemeralIPv4Network handles exception when address is setup.

        It performs no cleanup as the interface was already setup.
        """
        params = {
            "interface": "eth0",
            "ip": "10.85.130.116",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
            "interface_addrs_before_dhcp": example_netdev,
        }
        m_subp.side_effect = ProcessExecutionError(
            "", "RTNETLINK answers: File exists", 2
        )
        expected_calls = []
        with EphemeralIPv4Network(MockDistro(), **params):
            pass
        assert expected_calls == m_subp.call_args_list
        assert "Skip bringing up network link" in self.logs.getvalue()
        assert "Skip adding ip address" in self.logs.getvalue()

    def test_ephemeral_ipv4_network_with_prefix(self, m_subp):
        """EphemeralIPv4Network takes a valid prefix to setup the network."""
        params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "prefix_or_mask": "24",
            "broadcast": "192.168.2.255",
            "interface_addrs_before_dhcp": example_netdev,
        }
        for prefix_val in ["24", 16]:  # prefix can be int or string
            params["prefix_or_mask"] = prefix_val
            with EphemeralIPv4Network(MockDistro(), **params):
                pass
        m_subp.assert_has_calls(
            [
                mock.call(
                    [
                        "ip",
                        "-family",
                        "inet",
                        "addr",
                        "add",
                        "192.168.2.2/24",
                        "broadcast",
                        "192.168.2.255",
                        "dev",
                        "eth0",
                    ],
                    update_env={"LANG": "C"},
                )
            ]
        )
        m_subp.assert_has_calls(
            [
                mock.call(
                    [
                        "ip",
                        "-family",
                        "inet",
                        "addr",
                        "add",
                        "192.168.2.2/16",
                        "broadcast",
                        "192.168.2.255",
                        "dev",
                        "eth0",
                    ],
                    update_env={"LANG": "C"},
                )
            ]
        )

    def test_ephemeral_ipv4_network_with_new_default_route(self, m_subp):
        """Add the route when router is set and no default route exists."""
        params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
            "router": "192.168.2.1",
            "interface_addrs_before_dhcp": example_netdev,
        }
        # Empty response from ip route gw check
        m_subp.return_value = subp.SubpResult("", "")
        expected_setup_calls = [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "add",
                    "192.168.2.2/24",
                    "broadcast",
                    "192.168.2.255",
                    "dev",
                    "eth0",
                ],
                update_env={"LANG": "C"},
            ),
            mock.call(["ip", "route", "show", "0.0.0.0/0"]),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "replace",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                    "src",
                    "192.168.2.2",
                ],
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "replace",
                    "default",
                    "via",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                ],
            ),
        ]
        expected_teardown_calls = [
            mock.call(
                ["ip", "-4", "route", "del", "default", "dev", "eth0"],
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "del",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                    "src",
                    "192.168.2.2",
                ],
            ),
        ]

        with EphemeralIPv4Network(MockDistro(), **params):
            self.assertEqual(expected_setup_calls, m_subp.call_args_list)
        m_subp.assert_has_calls(expected_teardown_calls)

    def test_ephemeral_ipv4_network_with_rfc3442_static_routes(self, m_subp):
        params = {
            "interface": "eth0",
            "ip": "192.168.2.2",
            "prefix_or_mask": "255.255.255.255",
            "broadcast": "192.168.2.255",
            "static_routes": [
                ("192.168.2.1/32", "0.0.0.0"),
                ("169.254.169.254/32", "192.168.2.1"),
                ("0.0.0.0/0", "192.168.2.1"),
            ],
            "router": "192.168.2.1",
            "interface_addrs_before_dhcp": example_netdev,
        }
        expected_setup_calls = [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "add",
                    "192.168.2.2/32",
                    "broadcast",
                    "192.168.2.255",
                    "dev",
                    "eth0",
                ],
                update_env={"LANG": "C"},
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "append",
                    "192.168.2.1/32",
                    "dev",
                    "eth0",
                ],
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "append",
                    "169.254.169.254/32",
                    "via",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                ],
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "append",
                    "0.0.0.0/0",
                    "via",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                ],
            ),
        ]
        expected_teardown_calls = [
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "del",
                    "0.0.0.0/0",
                    "via",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                ],
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "del",
                    "169.254.169.254/32",
                    "via",
                    "192.168.2.1",
                    "dev",
                    "eth0",
                ],
            ),
            mock.call(
                ["ip", "-4", "route", "del", "192.168.2.1/32", "dev", "eth0"],
            ),
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "del",
                    "192.168.2.2/32",
                    "dev",
                    "eth0",
                ],
            ),
        ]
        with EphemeralIPv4Network(MockDistro(), **params):
            self.assertEqual(expected_setup_calls, m_subp.call_args_list)
        m_subp.assert_has_calls(expected_setup_calls + expected_teardown_calls)


class TestEphemeralIPV6Network:
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.subp.subp")
    def test_ephemeral_ipv6_network_performs_setup(self, m_subp, _):
        """EphemeralIPv4Network performs teardown on the device if setup."""
        expected_setup_calls = [
            mock.call(
                ["ip", "link", "set", "dev", "eth0", "up"],
            ),
        ]
        with EphemeralIPv6Network(MockDistro(), interface="eth0"):
            assert expected_setup_calls == m_subp.call_args_list


class TestHasURLConnectivity(ResponsesTestCase):
    def setUp(self):
        super(TestHasURLConnectivity, self).setUp()
        self.url = "http://fake/"
        self.kwargs = {"allow_redirects": True, "timeout": 5.0}

    @mock.patch("cloudinit.net.readurl")
    def test_url_timeout_on_connectivity_check(self, m_readurl):
        """A timeout of 5 seconds is provided when reading a url."""
        self.assertTrue(
            net.has_url_connectivity({"url": self.url}),
            "Expected True on url connect",
        )

    def test_true_on_url_connectivity_success(self):
        self.responses.add(responses.GET, self.url)
        self.assertTrue(
            net.has_url_connectivity({"url": self.url}),
            "Expected True on url connect",
        )

    @mock.patch("requests.Session.request")
    def test_true_on_url_connectivity_timeout(self, m_request):
        """A timeout raised accessing the url will return False."""
        m_request.side_effect = requests.Timeout("Fake Connection Timeout")
        self.assertFalse(
            net.has_url_connectivity({"url": self.url}),
            "Expected False on url timeout",
        )

    def test_true_on_url_connectivity_failure(self):
        self.responses.add(responses.GET, self.url, body=b"", status=404)
        self.assertFalse(
            net.has_url_connectivity({"url": self.url}),
            "Expected False on url fail",
        )


def _mk_v1_phys(mac, name, driver, device_id):
    v1_cfg = {"type": "physical", "name": name, "mac_address": mac}
    params = {}
    if driver:
        params.update({"driver": driver})
    if device_id:
        params.update({"device_id": device_id})

    if params:
        v1_cfg.update({"params": params})

    return v1_cfg


def _mk_v2_phys(mac, name, driver=None, device_id=None):
    v2_cfg = {"set-name": name, "match": {"macaddress": mac}}
    if driver:
        v2_cfg["match"].update({"driver": driver})
    if device_id:
        v2_cfg["match"].update({"device_id": device_id})

    return v2_cfg


class TestExtractPhysdevs(CiTestCase):
    def setUp(self):
        super(TestExtractPhysdevs, self).setUp()
        self.add_patch("cloudinit.net.device_driver", "m_driver")
        self.add_patch("cloudinit.net.device_devid", "m_devid")

    def test_extract_physdevs_looks_up_driver_v1(self):
        driver = "virtio"
        self.m_driver.return_value = driver
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", None, "0x1000"],
        ]
        netcfg = {
            "version": 1,
            "config": [_mk_v1_phys(*args) for args in physdevs],
        }
        # insert the driver value for verification
        physdevs[0][2] = driver
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )
        self.m_driver.assert_called_with("eth0")

    def test_extract_physdevs_looks_up_driver_v2(self):
        driver = "virtio"
        self.m_driver.return_value = driver
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", None, "0x1000"],
        ]
        netcfg = {
            "version": 2,
            "ethernets": {args[1]: _mk_v2_phys(*args) for args in physdevs},
        }
        # insert the driver value for verification
        physdevs[0][2] = driver
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )
        self.m_driver.assert_called_with("eth0")

    def test_extract_physdevs_looks_up_devid_v1(self):
        devid = "0x1000"
        self.m_devid.return_value = devid
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", "virtio", None],
        ]
        netcfg = {
            "version": 1,
            "config": [_mk_v1_phys(*args) for args in physdevs],
        }
        # insert the driver value for verification
        physdevs[0][3] = devid
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )
        self.m_devid.assert_called_with("eth0")

    def test_extract_physdevs_looks_up_devid_v2(self):
        devid = "0x1000"
        self.m_devid.return_value = devid
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", "virtio", None],
        ]
        netcfg = {
            "version": 2,
            "ethernets": {args[1]: _mk_v2_phys(*args) for args in physdevs},
        }
        # insert the driver value for verification
        physdevs[0][3] = devid
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )
        self.m_devid.assert_called_with("eth0")

    def test_get_v1_type_physical(self):
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", "virtio", "0x1000"],
            ["00:11:22:33:44:55", "ens3", "e1000", "0x1643"],
            ["09:87:65:43:21:10", "ens0p1", "mlx4_core", "0:0:1000"],
        ]
        netcfg = {
            "version": 1,
            "config": [_mk_v1_phys(*args) for args in physdevs],
        }
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )

    def test_get_v2_type_physical(self):
        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", "virtio", "0x1000"],
            ["00:11:22:33:44:55", "ens3", "e1000", "0x1643"],
            ["09:87:65:43:21:10", "ens0p1", "mlx4_core", "0:0:1000"],
        ]
        netcfg = {
            "version": 2,
            "ethernets": {args[1]: _mk_v2_phys(*args) for args in physdevs},
        }
        self.assertEqual(
            sorted(physdevs), sorted(net.extract_physdevs(netcfg))
        )

    def test_get_v2_type_physical_skips_if_no_set_name(self):
        netcfg = {
            "version": 2,
            "ethernets": {
                "ens3": {
                    "match": {"macaddress": "00:11:22:33:44:55"},
                }
            },
        }
        self.assertEqual([], net.extract_physdevs(netcfg))

    def test_runtime_error_on_unknown_netcfg_version(self):
        with self.assertRaises(RuntimeError):
            net.extract_physdevs({"version": 3, "awesome_config": []})


class TestNetFailOver:
    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        mocker.patch("cloudinit.net.util")
        self.device_driver = mocker.patch("cloudinit.net.device_driver")
        self.read_sys_net = mocker.patch("cloudinit.net.read_sys_net")

    def test_get_dev_features(self):
        devname = random_string()
        features = random_string()
        self.read_sys_net.return_value = features

        assert features == net.get_dev_features(devname)
        assert 1 == self.read_sys_net.call_count
        self.read_sys_net.assert_called_once_with(devname, "device/features")

    def test_get_dev_features_none_returns_empty_string(self):
        devname = random_string()
        self.read_sys_net.side_effect = Exception("error")
        assert "" == net.get_dev_features(devname)
        assert 1 == self.read_sys_net.call_count
        self.read_sys_net.assert_called_once_with(devname, "device/features")

    @mock.patch("cloudinit.net.get_dev_features")
    def test_has_netfail_standby_feature(self, m_dev_features):
        devname = random_string()
        standby_features = ("0" * 62) + "1" + "0"
        m_dev_features.return_value = standby_features
        assert net.has_netfail_standby_feature(devname)

    @mock.patch("cloudinit.net.get_dev_features")
    def test_has_netfail_standby_feature_short_is_false(self, m_dev_features):
        devname = random_string()
        standby_features = random_string()
        m_dev_features.return_value = standby_features
        assert not net.has_netfail_standby_feature(devname)

    @mock.patch("cloudinit.net.get_dev_features")
    def test_has_netfail_standby_feature_not_present_is_false(
        self, m_dev_features
    ):
        devname = random_string()
        standby_features = "0" * 64
        m_dev_features.return_value = standby_features
        assert not net.has_netfail_standby_feature(devname)

    @mock.patch("cloudinit.net.get_dev_features")
    def test_has_netfail_standby_feature_no_features_is_false(
        self, m_dev_features
    ):
        devname = random_string()
        standby_features = None
        m_dev_features.return_value = standby_features
        assert not net.has_netfail_standby_feature(devname)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_master(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = False  # no master sysfs attr
        m_standby.return_value = True  # has standby feature flag
        assert net.is_netfail_master(devname, driver)

    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_master_checks_master_attr(self, m_sysdev):
        devname = random_string()
        driver = "virtio_net"
        m_sysdev.return_value = random_string()
        assert not net.is_netfail_master(devname, driver)
        assert 1 == m_sysdev.call_count
        m_sysdev.assert_called_once_with(devname, path="master")

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_master_wrong_driver(self, m_exists, m_standby):
        devname = random_string()
        driver = random_string()
        assert not net.is_netfail_master(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_master_has_master_attr(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = True  # has master sysfs attr
        assert not net.is_netfail_master(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_master_no_standby_feat(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = False  # no master sysfs attr
        m_standby.return_value = False  # no standby feature flag
        assert not net.is_netfail_master(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_primary(self, m_sysdev, m_exists, m_standby):
        devname = random_string()
        driver = random_string()  # device not virtio_net
        master_devname = random_string()
        m_sysdev.return_value = "%s/%s" % (
            random_string(),
            master_devname,
        )
        m_exists.return_value = True  # has master sysfs attr
        self.device_driver.return_value = "virtio_net"  # master virtio_net
        m_standby.return_value = True  # has standby feature flag
        assert net.is_netfail_primary(devname, driver)
        self.device_driver.assert_called_once_with(master_devname)
        assert 1 == m_standby.call_count
        m_standby.assert_called_once_with(master_devname)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_primary_wrong_driver(
        self, m_sysdev, m_exists, m_standby
    ):
        devname = random_string()
        driver = "virtio_net"
        assert not net.is_netfail_primary(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_primary_no_master(self, m_sysdev, m_exists, m_standby):
        devname = random_string()
        driver = random_string()  # device not virtio_net
        m_exists.return_value = False  # no master sysfs attr
        assert not net.is_netfail_primary(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_primary_bad_master(
        self, m_sysdev, m_exists, m_standby
    ):
        devname = random_string()
        driver = random_string()  # device not virtio_net
        master_devname = random_string()
        m_sysdev.return_value = "%s/%s" % (
            random_string(),
            master_devname,
        )
        m_exists.return_value = True  # has master sysfs attr
        self.device_driver.return_value = "XXXX"  # master not virtio_net
        assert not net.is_netfail_primary(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    @mock.patch("cloudinit.net.sys_dev_path")
    def test_is_netfail_primary_no_standby(
        self, m_sysdev, m_exists, m_standby
    ):
        devname = random_string()
        driver = random_string()  # device not virtio_net
        master_devname = random_string()
        m_sysdev.return_value = "%s/%s" % (
            random_string(),
            master_devname,
        )
        m_exists.return_value = True  # has master sysfs attr
        self.device_driver.return_value = "virtio_net"  # master virtio_net
        m_standby.return_value = False  # master has no standby feature flag
        assert not net.is_netfail_primary(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_standby(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = True  # has master sysfs attr
        m_standby.return_value = True  # has standby feature flag
        assert net.is_netfail_standby(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_standby_wrong_driver(self, m_exists, m_standby):
        devname = random_string()
        driver = random_string()
        assert not net.is_netfail_standby(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_standby_no_master(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = False  # has master sysfs attr
        assert not net.is_netfail_standby(devname, driver)

    @mock.patch("cloudinit.net.has_netfail_standby_feature")
    @mock.patch("cloudinit.net.os.path.exists")
    def test_is_netfail_standby_no_standby_feature(self, m_exists, m_standby):
        devname = random_string()
        driver = "virtio_net"
        m_exists.return_value = True  # has master sysfs attr
        m_standby.return_value = False  # has standby feature flag
        assert not net.is_netfail_standby(devname, driver)

    @mock.patch("cloudinit.net.is_netfail_standby")
    @mock.patch("cloudinit.net.is_netfail_primary")
    def test_is_netfailover_primary(self, m_primary, m_standby):
        devname = random_string()
        driver = random_string()
        m_primary.return_value = True
        m_standby.return_value = False
        assert net.is_netfailover(devname, driver)

    @mock.patch("cloudinit.net.is_netfail_standby")
    @mock.patch("cloudinit.net.is_netfail_primary")
    def test_is_netfailover_standby(self, m_primary, m_standby):
        devname = random_string()
        driver = random_string()
        m_primary.return_value = False
        m_standby.return_value = True
        assert net.is_netfailover(devname, driver)

    @mock.patch("cloudinit.net.is_netfail_standby")
    @mock.patch("cloudinit.net.is_netfail_primary")
    def test_is_netfailover_returns_false(self, m_primary, m_standby):
        devname = random_string()
        driver = random_string()
        m_primary.return_value = False
        m_standby.return_value = False
        assert not net.is_netfailover(devname, driver)


class TestOpenvswitchIsInstalled:
    """Test cloudinit.net.openvswitch_is_installed.

    Uses the ``clear_lru_cache`` local autouse fixture to allow us to test
    despite the ``lru_cache`` decorator on the unit under test.
    """

    @pytest.fixture(autouse=True)
    def clear_lru_cache(self):
        net.openvswitch_is_installed.cache_clear()

    @pytest.mark.parametrize(
        "expected,which_return", [(True, "/some/path"), (False, None)]
    )
    @mock.patch("cloudinit.net.subp.which")
    def test_mirrors_which_result(self, m_which, expected, which_return):
        m_which.return_value = which_return
        assert expected == net.openvswitch_is_installed()

    @mock.patch("cloudinit.net.subp.which")
    def test_only_calls_which_once(self, m_which):
        net.openvswitch_is_installed()
        net.openvswitch_is_installed()
        assert 1 == m_which.call_count


@mock.patch("cloudinit.net.subp.subp", return_value=("", ""))
class TestGetOVSInternalInterfaces:
    """Test cloudinit.net.get_ovs_internal_interfaces.

    Uses the ``clear_lru_cache`` local autouse fixture to allow us to test
    despite the ``lru_cache`` decorator on the unit under test.
    """

    @pytest.fixture(autouse=True)
    def clear_lru_cache(self):
        net.get_ovs_internal_interfaces.cache_clear()

    def test_command_used(self, m_subp):
        """Test we use the correct command when we call subp"""
        net.get_ovs_internal_interfaces()

        assert [
            mock.call(net.OVS_INTERNAL_INTERFACE_LOOKUP_CMD)
        ] == m_subp.call_args_list

    def test_subp_contents_split_and_returned(self, m_subp):
        """Test that the command output is appropriately mangled."""
        stdout = "iface1\niface2\niface3\n"
        m_subp.return_value = (stdout, "")

        assert [
            "iface1",
            "iface2",
            "iface3",
        ] == net.get_ovs_internal_interfaces()

    def test_database_connection_error_handled_gracefully(self, m_subp):
        """Test that the error indicating OVS is down is handled gracefully."""
        m_subp.side_effect = ProcessExecutionError(
            stderr="database connection failed"
        )

        assert [] == net.get_ovs_internal_interfaces()

    def test_other_errors_raised(self, m_subp):
        """Test that only database connection errors are handled."""
        m_subp.side_effect = ProcessExecutionError()

        with pytest.raises(ProcessExecutionError):
            net.get_ovs_internal_interfaces()

    def test_only_runs_once(self, m_subp):
        """Test that we cache the value."""
        net.get_ovs_internal_interfaces()
        net.get_ovs_internal_interfaces()

        assert 1 == m_subp.call_count


@mock.patch("cloudinit.net.get_ovs_internal_interfaces")
@mock.patch("cloudinit.net.openvswitch_is_installed")
class TestIsOpenVSwitchInternalInterface:
    def test_false_if_ovs_not_installed(
        self, m_openvswitch_is_installed, _m_get_ovs_internal_interfaces
    ):
        """Test that OVS' absence returns False."""
        m_openvswitch_is_installed.return_value = False

        assert not net.is_openvswitch_internal_interface("devname")

    @pytest.mark.parametrize(
        "detected_interfaces,devname,expected_return",
        [
            ([], "devname", False),
            (["notdevname"], "devname", False),
            (["devname"], "devname", True),
            (["some", "other", "devices", "and", "ours"], "ours", True),
        ],
    )
    def test_return_value_based_on_detected_interfaces(
        self,
        m_openvswitch_is_installed,
        m_get_ovs_internal_interfaces,
        detected_interfaces,
        devname,
        expected_return,
    ):
        """Test that the detected interfaces are used correctly."""
        m_openvswitch_is_installed.return_value = True
        m_get_ovs_internal_interfaces.return_value = detected_interfaces
        assert expected_return == net.is_openvswitch_internal_interface(
            devname
        )


class TestIsIpAddress:
    """Tests for net.is_ip_address.

    Instead of testing with values we rely on the ipaddress stdlib module to
    handle all values correctly, so simply test that is_ip_address defers to
    the ipaddress module correctly.
    """

    @pytest.mark.parametrize(
        "ip_address_side_effect,expected_return",
        (
            (ValueError, False),
            (lambda _: ipaddress.IPv4Address("192.168.0.1"), True),
            (lambda _: ipaddress.IPv4Address("192.168.0.1/24"), False),
            (lambda _: ipaddress.IPv6Address("2001:db8::"), True),
            (lambda _: ipaddress.IPv6Address("2001:db8::/48"), False),
        ),
    )
    def test_is_ip_address(self, ip_address_side_effect, expected_return):
        with mock.patch(
            "cloudinit.net.ipaddress.ip_address",
            side_effect=ip_address_side_effect,
        ) as m_ip_address:
            ret = net.is_ip_address(mock.sentinel.ip_address_in)
        assert expected_return == ret
        expected_call = mock.call(mock.sentinel.ip_address_in)
        assert [expected_call] == m_ip_address.call_args_list


class TestIsIpv4Address:
    """Tests for net.is_ipv4_address.

    Instead of testing with values we rely on the ipaddress stdlib module to
    handle all values correctly, so simply test that is_ipv4_address defers to
    the ipaddress module correctly.
    """

    @pytest.mark.parametrize(
        "ipv4address_mock,expected_return",
        (
            (mock.Mock(side_effect=ValueError), False),
            (
                mock.Mock(return_value=ipaddress.IPv4Address("192.168.0.1")),
                True,
            ),
        ),
    )
    def test_is_ip_address(self, ipv4address_mock, expected_return):
        with mock.patch(
            "cloudinit.net.ipaddress.IPv4Address", ipv4address_mock
        ) as m_ipv4address:
            ret = net.is_ipv4_address(mock.sentinel.ip_address_in)
        assert expected_return == ret
        expected_call = mock.call(mock.sentinel.ip_address_in)
        assert [expected_call] == m_ipv4address.call_args_list


class TestIsIpNetwork:
    """Tests for net.is_ip_network() and related functions."""

    @pytest.mark.parametrize(
        "func,arg,expected_return",
        (
            (net.is_ip_network, "192.168.1.1", True),
            (net.is_ip_network, "192.168.1.1/24", True),
            (net.is_ip_network, "192.168.1.1/32", True),
            (net.is_ip_network, "192.168.1.1/33", False),
            (net.is_ip_network, "2001:67c:1", False),
            (net.is_ip_network, "2001:67c:1/32", False),
            (net.is_ip_network, "2001:67c::", True),
            (net.is_ip_network, "2001:67c::/32", True),
            (net.is_ipv4_network, "192.168.1.1", True),
            (net.is_ipv4_network, "192.168.1.1/24", True),
            (net.is_ipv4_network, "2001:67c::", False),
            (net.is_ipv4_network, "2001:67c::/32", False),
            (net.is_ipv6_network, "192.168.1.1", False),
            (net.is_ipv6_network, "192.168.1.1/24", False),
            (net.is_ipv6_network, "2001:67c:1", False),
            (net.is_ipv6_network, "2001:67c:1/32", False),
            (net.is_ipv6_network, "2001:67c::", True),
            (net.is_ipv6_network, "2001:67c::/32", True),
            (net.is_ipv6_network, "2001:67c::/129", False),
            (net.is_ipv6_network, "2001:67c::/128", True),
        ),
    )
    def test_is_ip_network(self, func, arg, expected_return):
        assert func(arg) == expected_return


class TestIsIpInSubnet:
    """Tests for net.is_ip_in_subnet()."""

    @pytest.mark.parametrize(
        "func,ip,subnet,expected_return",
        (
            (net.is_ip_in_subnet, "192.168.1.1", "2001:67c::1/64", False),
            (net.is_ip_in_subnet, "2001:67c::1", "192.168.1.1/24", False),
            (net.is_ip_in_subnet, "192.168.1.1", "192.168.1.1/24", True),
            (net.is_ip_in_subnet, "192.168.1.1", "192.168.1.1/32", True),
            (net.is_ip_in_subnet, "192.168.1.2", "192.168.1.1/24", True),
            (net.is_ip_in_subnet, "192.168.1.2", "192.168.1.1/32", False),
            (net.is_ip_in_subnet, "192.168.2.2", "192.168.1.1/24", False),
            (net.is_ip_in_subnet, "192.168.2.2", "192.168.1.1/32", False),
            (net.is_ip_in_subnet, "2001:67c1::1", "2001:67c1::1/64", True),
            (net.is_ip_in_subnet, "2001:67c1::1", "2001:67c1::1/128", True),
            (net.is_ip_in_subnet, "2001:67c1::2", "2001:67c1::1/64", True),
            (net.is_ip_in_subnet, "2001:67c1::2", "2001:67c1::1/128", False),
            (net.is_ip_in_subnet, "2002:67c1::1", "2001:67c1::1/8", True),
            (net.is_ip_in_subnet, "2002:67c1::1", "2001:67c1::1/16", False),
        ),
    )
    def test_is_ip_in_subnet(self, func, ip, subnet, expected_return):
        assert func(ip, subnet) == expected_return
