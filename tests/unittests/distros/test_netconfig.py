# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os
import re
from io import StringIO
from textwrap import dedent
from unittest import mock

from cloudinit import (
    distros,
    features,
    helpers,
    safeyaml,
    settings,
    subp,
    util,
)
from cloudinit.distros.parsers.sys_conf import SysConf
from cloudinit.net.activators import IfUpDownActivator
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    dir2dict,
    readResource,
)

BASE_NET_CFG = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5
    broadcast 192.168.1.0
    gateway 192.168.1.254
    netmask 255.255.255.0
    network 192.168.0.0

auto eth1
iface eth1 inet dhcp
"""

BASE_NET_CFG_FROM_V2 = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5/24
    gateway 192.168.1.254

auto eth1
iface eth1 inet dhcp
"""

BASE_NET_CFG_IPV6 = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5
    netmask 255.255.255.0
    network 192.168.0.0
    broadcast 192.168.1.0
    gateway 192.168.1.254

iface eth0 inet6 static
    address 2607:f0d0:1002:0011::2
    netmask 64
    gateway 2607:f0d0:1002:0011::1

iface eth1 inet static
    address 192.168.1.6
    netmask 255.255.255.0
    network 192.168.0.0
    broadcast 192.168.1.0
    gateway 192.168.1.254

iface eth1 inet6 static
    address 2607:f0d0:1002:0011::3
    netmask 64
    gateway 2607:f0d0:1002:0011::1
"""

V1_NET_CFG = {
    "config": [
        {
            "name": "eth0",
            "subnets": [
                {
                    "address": "192.168.1.5",
                    "broadcast": "192.168.1.0",
                    "gateway": "192.168.1.254",
                    "netmask": "255.255.255.0",
                    "type": "static",
                }
            ],
            "type": "physical",
        },
        {
            "name": "eth1",
            "subnets": [{"control": "auto", "type": "dhcp4"}],
            "type": "physical",
        },
    ],
    "version": 1,
}

V1_NET_CFG_WITH_DUPS = """\
# same value in interface specific dns and global dns
# should produce single entry in network file
version: 1
config:
    - type: physical
      name: eth0
      subnets:
          - type: static
            address: 192.168.0.102/24
            dns_nameservers: [1.2.3.4]
            dns_search: [test.com]
            interface: eth0
    - type: nameserver
      address: [1.2.3.4]
      search: [test.com]
"""

V1_NET_CFG_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5/24
    broadcast 192.168.1.0
    gateway 192.168.1.254

auto eth1
iface eth1 inet dhcp
"""

V1_NET_CFG_IPV6_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet6 static
    address 2607:f0d0:1002:0011::2/64
    gateway 2607:f0d0:1002:0011::1

auto eth1
iface eth1 inet dhcp
"""

V1_NET_CFG_IPV6 = {
    "config": [
        {
            "name": "eth0",
            "subnets": [
                {
                    "address": "2607:f0d0:1002:0011::2",
                    "gateway": "2607:f0d0:1002:0011::1",
                    "netmask": "64",
                    "type": "static6",
                }
            ],
            "type": "physical",
        },
        {
            "name": "eth1",
            "subnets": [{"control": "auto", "type": "dhcp4"}],
            "type": "physical",
        },
    ],
    "version": 1,
}


V1_TO_V2_NET_CFG_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    version: 2
    ethernets:
        eth0:
            addresses:
            - 192.168.1.5/24
            routes:
            -   to: default
                via: 192.168.1.254
        eth1:
            dhcp4: true
"""

V1_TO_V2_NET_CFG_IPV6_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    version: 2
    ethernets:
        eth0:
            addresses:
            - 2607:f0d0:1002:0011::2/64
            routes:
            -   to: default
                via: 2607:f0d0:1002:0011::1
        eth1:
            dhcp4: true
"""

V2_NET_CFG = {
    "ethernets": {
        "eth7": {"addresses": ["192.168.1.5/24"], "gateway4": "192.168.1.254"},
        "eth9": {"dhcp4": True},
    },
    "version": 2,
}


V2_TO_V2_NET_CFG_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    ethernets:
        eth7:
            addresses:
            - 192.168.1.5/24
            gateway4: 192.168.1.254
        eth9:
            dhcp4: true
    version: 2
"""


V2_PASSTHROUGH_NET_CFG = {
    "ethernets": {
        "eth7": {
            "addresses": ["192.168.1.5/24"],
            "gateway4": "192.168.1.254",
            "routes": [{"to": "default", "via": "10.0.4.1", "metric": 100}],
        },
    },
    "version": 2,
}


V2_PASSTHROUGH_NET_CFG_OUTPUT = """\
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    ethernets:
        eth7:
            addresses:
            - 192.168.1.5/24
            gateway4: 192.168.1.254
            routes:
            -   metric: 100
                to: default
                via: 10.0.4.1
    version: 2
"""


class WriteBuffer:
    def __init__(self):
        self.buffer = StringIO()
        self.mode = None
        self.omode = None

    def write(self, text):
        self.buffer.write(text)

    def __str__(self):
        return self.buffer.getvalue()


class TestNetCfgDistroBase(FilesystemMockingTestCase):
    def setUp(self):
        super(TestNetCfgDistroBase, self).setUp()
        self.add_patch("cloudinit.util.system_is_snappy", "m_snappy")

    def _get_distro(self, dname, renderers=None, activators=None):
        cls = distros.fetch(dname)
        cfg = settings.CFG_BUILTIN
        cfg["system_info"]["distro"] = dname
        system_info_network_cfg = {}
        if renderers:
            system_info_network_cfg["renderers"] = renderers
        if activators:
            system_info_network_cfg["activators"] = activators
        if system_info_network_cfg:
            cfg["system_info"]["network"] = system_info_network_cfg
        paths = helpers.Paths({})
        return cls(dname, cfg.get("system_info"), paths)

    def assertCfgEquals(self, blob1, blob2):
        b1 = dict(SysConf(blob1.strip().splitlines()))
        b2 = dict(SysConf(blob2.strip().splitlines()))
        self.assertEqual(b1, b2)
        for (k, v) in b1.items():
            self.assertIn(k, b2)
        for (k, v) in b2.items():
            self.assertIn(k, b1)
        for (k, v) in b1.items():
            self.assertEqual(v, b2[k])


class TestNetCfgDistroFreeBSD(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroFreeBSD, self).setUp()
        ifs_txt = readResource("netinfo/freebsd-ifconfig-output")
        with mock.patch(
            "cloudinit.distros.networking.subp.subp",
            return_value=(ifs_txt, None),
        ):
            self.distro = self._get_distro("freebsd", renderers=["freebsd"])

    def _apply_and_verify_freebsd(
        self, apply_fn, config, expected_cfgs=None, bringup=False
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.freebsd.available") as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                util.ensure_dir("/etc")
                util.ensure_file("/etc/rc.conf")
                util.ensure_file("/etc/resolv.conf")
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(
                set(expected.split("\n")), set(results[cfgpath].split("\n"))
            )
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_apply_network_config_freebsd_standard(self, ifaces_mac):
        ifaces_mac.return_value = {
            "00:15:5d:4c:73:00": "eth0",
        }
        rc_conf_expected = """\
defaultrouter=192.168.1.254
ifconfig_eth0='inet 192.168.1.5 netmask 255.255.255.0'
ifconfig_eth1=DHCP
"""

        expected_cfgs = {
            "/etc/rc.conf": rc_conf_expected,
            "/etc/resolv.conf": "",
        }
        self._apply_and_verify_freebsd(
            self.distro.apply_network_config,
            V1_NET_CFG,
            expected_cfgs=expected_cfgs.copy(),
        )

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_apply_network_config_freebsd_ipv6_standard(self, ifaces_mac):
        ifaces_mac.return_value = {
            "00:15:5d:4c:73:00": "eth0",
        }
        rc_conf_expected = """\
ipv6_defaultrouter=2607:f0d0:1002:0011::1
ifconfig_eth1=DHCP
ifconfig_eth0_ipv6='inet6 2607:f0d0:1002:0011::2/64'
"""

        expected_cfgs = {
            "/etc/rc.conf": rc_conf_expected,
            "/etc/resolv.conf": "",
        }
        self._apply_and_verify_freebsd(
            self.distro.apply_network_config,
            V1_NET_CFG_IPV6,
            expected_cfgs=expected_cfgs.copy(),
        )

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_apply_network_config_freebsd_ifrename(self, ifaces_mac):
        ifaces_mac.return_value = {
            "00:15:5d:4c:73:00": "vtnet0",
        }
        rc_conf_expected = """\
ifconfig_vtnet0_name=eth0
defaultrouter=192.168.1.254
ifconfig_eth0='inet 192.168.1.5 netmask 255.255.255.0'
ifconfig_eth1=DHCP
"""

        V1_NET_CFG_RENAME = copy.deepcopy(V1_NET_CFG)
        V1_NET_CFG_RENAME["config"][0]["mac_address"] = "00:15:5d:4c:73:00"

        expected_cfgs = {
            "/etc/rc.conf": rc_conf_expected,
            "/etc/resolv.conf": "",
        }
        self._apply_and_verify_freebsd(
            self.distro.apply_network_config,
            V1_NET_CFG_RENAME,
            expected_cfgs=expected_cfgs.copy(),
        )

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_apply_network_config_freebsd_nameserver(self, ifaces_mac):
        ifaces_mac.return_value = {
            "00:15:5d:4c:73:00": "eth0",
        }

        V1_NET_CFG_DNS = copy.deepcopy(V1_NET_CFG)
        ns = ["1.2.3.4"]
        V1_NET_CFG_DNS["config"][0]["subnets"][0]["dns_nameservers"] = ns
        expected_cfgs = {"/etc/resolv.conf": "nameserver 1.2.3.4\n"}
        self._apply_and_verify_freebsd(
            self.distro.apply_network_config,
            V1_NET_CFG_DNS,
            expected_cfgs=expected_cfgs.copy(),
        )


class TestNetCfgDistroUbuntuEni(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroUbuntuEni, self).setUp()
        self.distro = self._get_distro(
            "ubuntu", renderers=["eni"], activators=["eni"]
        )

    def eni_path(self):
        return "/etc/network/interfaces.d/50-cloud-init.cfg"

    def rules_path(self):
        return "/etc/udev/rules.d/70-persistent-net.rules"

    def _apply_and_verify_eni(
        self,
        apply_fn,
        config,
        expected_cfgs=None,
        bringup=False,
        previous_files=(),
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.eni.available") as m_avail:
            m_avail.return_value = True
            path_modes = {}
            with self.reRooted(tmpd) as tmpd:
                for previous_path, content, mode in previous_files:
                    util.write_file(previous_path, content, mode=mode)
                    path_modes[previous_path] = mode
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(expected, results[cfgpath])
            self.assertEqual(
                path_modes.get(cfgpath, 0o644), get_mode(cfgpath, tmpd)
            )

    def test_apply_network_config_and_bringup_filters_priority_eni_ub(self):
        """Network activator search priority can be overridden from config."""
        expected_cfgs = {
            self.eni_path(): V1_NET_CFG_OUTPUT,
        }
        with mock.patch(
            "cloudinit.net.activators.select_activator"
        ) as select_activator:
            select_activator.return_value = IfUpDownActivator
            self._apply_and_verify_eni(
                self.distro.apply_network_config,
                V1_NET_CFG,
                expected_cfgs=expected_cfgs.copy(),
                bringup=True,
            )
            # 2nd call to select_activator via distro.network_activator prop
            assert IfUpDownActivator == self.distro.network_activator
        self.assertEqual(
            [mock.call(priority=["eni"])] * 2, select_activator.call_args_list
        )

    def test_apply_network_config_and_bringup_activator_defaults_ub(self):
        """Network activator search priority defaults when unspecified."""
        expected_cfgs = {
            self.eni_path(): V1_NET_CFG_OUTPUT,
        }
        # Don't set activators to see DEFAULT_PRIORITY
        self.distro = self._get_distro("ubuntu", renderers=["eni"])
        with mock.patch(
            "cloudinit.net.activators.select_activator"
        ) as select_activator:
            select_activator.return_value = IfUpDownActivator
            self._apply_and_verify_eni(
                self.distro.apply_network_config,
                V1_NET_CFG,
                expected_cfgs=expected_cfgs.copy(),
                bringup=True,
            )
            # 2nd call to select_activator via distro.network_activator prop
            assert IfUpDownActivator == self.distro.network_activator
        self.assertEqual(
            [mock.call(priority=None)] * 2, select_activator.call_args_list
        )

    def test_apply_network_config_eni_ub(self):
        expected_cfgs = {
            self.eni_path(): V1_NET_CFG_OUTPUT,
            self.rules_path(): "",
        }
        self._apply_and_verify_eni(
            self.distro.apply_network_config,
            V1_NET_CFG,
            expected_cfgs=expected_cfgs.copy(),
            previous_files=((self.rules_path(), "something", 0o660),),
        )

    def test_apply_network_config_ipv6_ub(self):
        expected_cfgs = {self.eni_path(): V1_NET_CFG_IPV6_OUTPUT}
        self._apply_and_verify_eni(
            self.distro.apply_network_config,
            V1_NET_CFG_IPV6,
            expected_cfgs=expected_cfgs.copy(),
        )


class TestNetCfgDistroUbuntuNetplan(TestNetCfgDistroBase):

    with_logs = True

    def setUp(self):
        super(TestNetCfgDistroUbuntuNetplan, self).setUp()
        self.distro = self._get_distro("ubuntu", renderers=["netplan"])
        self.devlist = ["eth0", "lo"]

    def _apply_and_verify_netplan(
        self,
        apply_fn,
        config,
        expected_cfgs=None,
        bringup=False,
        previous_files=(),
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.netplan.available", return_value=True):
            with mock.patch(
                "cloudinit.net.netplan.get_devicelist",
                return_value=self.devlist,
            ):
                with self.reRooted(tmpd) as tmpd:
                    for previous_path, content, mode in previous_files:
                        util.write_file(previous_path, content, mode=mode)
                    apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected, mode in expected_cfgs:
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(expected, results[cfgpath])
            self.assertEqual(mode, get_mode(cfgpath, tmpd))

    def netplan_path(self):
        return "/etc/netplan/50-cloud-init.yaml"

    def test_apply_network_config_v1_to_netplan_ub(self):
        expected_cfgs = (
            (self.netplan_path(), V1_TO_V2_NET_CFG_OUTPUT, 0o600),
        )

        self._apply_and_verify_netplan(
            self.distro.apply_network_config,
            V1_NET_CFG,
            expected_cfgs=expected_cfgs,
        )

    def test_apply_network_config_v1_ipv6_to_netplan_ub(self):
        expected_cfgs = (
            (self.netplan_path(), V1_TO_V2_NET_CFG_IPV6_OUTPUT, 0o600),
        )

        self._apply_and_verify_netplan(
            self.distro.apply_network_config,
            V1_NET_CFG_IPV6,
            expected_cfgs=expected_cfgs,
        )

    def test_apply_network_config_v2_passthrough_ub(self):
        expected_cfgs = (
            (self.netplan_path(), V2_TO_V2_NET_CFG_OUTPUT, 0o600),
        )
        self._apply_and_verify_netplan(
            self.distro.apply_network_config,
            V2_NET_CFG,
            expected_cfgs=expected_cfgs,
        )

    def test_apply_network_config_v2_passthrough_retain_orig_perms(self):
        """Custom permissions on existing netplan is kept when more strict."""
        expected_cfgs = (
            (self.netplan_path(), V2_TO_V2_NET_CFG_OUTPUT, 0o640),
        )
        with mock.patch.object(
            features, "NETPLAN_CONFIG_ROOT_READ_ONLY", False
        ):
            # When NETPLAN_CONFIG_ROOT_READ_ONLY is False default perms are 644
            # we keep 640 because it's more strict.
            # 1640 is used to assert sticky bit preserved across write
            self._apply_and_verify_netplan(
                self.distro.apply_network_config,
                V2_NET_CFG,
                expected_cfgs=expected_cfgs,
                previous_files=(
                    ("/etc/netplan/50-cloud-init.yaml", "a", 0o640),
                ),
            )

    def test_apply_network_config_v2_passthrough_ub_old_behavior(self):
        """Kinetic and earlier have 50-cloud-init.yaml world-readable"""
        expected_cfgs = (
            (self.netplan_path(), V2_TO_V2_NET_CFG_OUTPUT, 0o644),
        )
        with mock.patch.object(
            features, "NETPLAN_CONFIG_ROOT_READ_ONLY", False
        ):
            self._apply_and_verify_netplan(
                self.distro.apply_network_config,
                V2_NET_CFG,
                expected_cfgs=expected_cfgs,
            )

    def test_apply_network_config_v2_full_passthrough_ub(self):
        expected_cfgs = (
            (self.netplan_path(), V2_PASSTHROUGH_NET_CFG_OUTPUT, 0o600),
        )
        self._apply_and_verify_netplan(
            self.distro.apply_network_config,
            V2_PASSTHROUGH_NET_CFG,
            expected_cfgs=expected_cfgs,
        )
        self.assertIn("Passthrough netplan v2 config", self.logs.getvalue())
        self.assertIn(
            "Selected renderer 'netplan' from priority list: ['netplan']",
            self.logs.getvalue(),
        )


class TestNetCfgDistroRedhat(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroRedhat, self).setUp()
        self.distro = self._get_distro("rhel", renderers=["sysconfig"])

    def ifcfg_path(self, ifname):
        return "/etc/sysconfig/network-scripts/ifcfg-%s" % ifname

    def control_path(self):
        return "/etc/sysconfig/network"

    def _apply_and_verify(
        self, apply_fn, config, expected_cfgs=None, bringup=False
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.sysconfig.available") as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            self.assertCfgEquals(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def test_apply_network_config_rh(self):
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0
                GATEWAY=192.168.1.254
                IPADDR=192.168.1.5
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.ifcfg_path("eth1"): dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.control_path(): dedent(
                """\
                NETWORKING=yes
                """
            ),
        }
        # rh_distro.apply_network_config(V1_NET_CFG, False)
        self._apply_and_verify(
            self.distro.apply_network_config,
            V1_NET_CFG,
            expected_cfgs=expected_cfgs.copy(),
        )

    def test_apply_network_config_ipv6_rh(self):
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0
                IPV6ADDR=2607:f0d0:1002:0011::2/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_DEFAULTGW=2607:f0d0:1002:0011::1
                IPV6_FORCE_ACCEPT_RA=no
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.ifcfg_path("eth1"): dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.control_path(): dedent(
                """\
                NETWORKING=yes
                NETWORKING_IPV6=yes
                IPV6_AUTOCONF=no
                """
            ),
        }
        # rh_distro.apply_network_config(V1_NET_CFG_IPV6, False)
        self._apply_and_verify(
            self.distro.apply_network_config,
            V1_NET_CFG_IPV6,
            expected_cfgs=expected_cfgs.copy(),
        )

    def test_vlan_render_unsupported(self):
        """Render officially unsupported vlan names."""
        cfg = {
            "version": 2,
            "ethernets": {
                "eth0": {
                    "addresses": ["192.10.1.2/24"],
                    "match": {"macaddress": "00:16:3e:60:7c:df"},
                }
            },
            "vlans": {
                "infra0": {
                    "addresses": ["10.0.1.2/16"],
                    "id": 1001,
                    "link": "eth0",
                }
            },
        }
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=00:16:3e:60:7c:df
                IPADDR=192.10.1.2
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.ifcfg_path("infra0"): dedent(
                """\
                BOOTPROTO=none
                DEVICE=infra0
                IPADDR=10.0.1.2
                NETMASK=255.255.0.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=eth0
                USERCTL=no
                VLAN=yes
                """
            ),
            self.control_path(): dedent(
                """\
                NETWORKING=yes
                """
            ),
        }
        self._apply_and_verify(
            self.distro.apply_network_config, cfg, expected_cfgs=expected_cfgs
        )

    def test_vlan_render(self):
        cfg = {
            "version": 2,
            "ethernets": {"eth0": {"addresses": ["192.10.1.2/24"]}},
            "vlans": {
                "eth0.1001": {
                    "addresses": ["10.0.1.2/16"],
                    "id": 1001,
                    "link": "eth0",
                }
            },
        }
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                IPADDR=192.10.1.2
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            self.ifcfg_path("eth0.1001"): dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0.1001
                IPADDR=10.0.1.2
                NETMASK=255.255.0.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=eth0
                USERCTL=no
                VLAN=yes
                """
            ),
            self.control_path(): dedent(
                """\
                NETWORKING=yes
                """
            ),
        }
        self._apply_and_verify(
            self.distro.apply_network_config, cfg, expected_cfgs=expected_cfgs
        )


class TestNetCfgDistroOpensuse(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroOpensuse, self).setUp()
        self.distro = self._get_distro("opensuse", renderers=["sysconfig"])

    def ifcfg_path(self, ifname):
        return "/etc/sysconfig/network/ifcfg-%s" % ifname

    def _apply_and_verify(
        self, apply_fn, config, expected_cfgs=None, bringup=False
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.sysconfig.available") as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            self.assertCfgEquals(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def test_apply_network_config_opensuse(self):
        """Opensuse uses apply_network_config and renders sysconfig"""
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.1.5
                NETMASK=255.255.255.0
                STARTMODE=auto
                """
            ),
            self.ifcfg_path("eth1"): dedent(
                """\
                BOOTPROTO=dhcp4
                STARTMODE=auto
                """
            ),
        }
        self._apply_and_verify(
            self.distro.apply_network_config,
            V1_NET_CFG,
            expected_cfgs=expected_cfgs.copy(),
        )

    def test_apply_network_config_ipv6_opensuse(self):
        """Opensuse uses apply_network_config and renders sysconfig w/ipv6"""
        expected_cfgs = {
            self.ifcfg_path("eth0"): dedent(
                """\
                BOOTPROTO=static
                IPADDR6=2607:f0d0:1002:0011::2/64
                STARTMODE=auto
            """
            ),
            self.ifcfg_path("eth1"): dedent(
                """\
                BOOTPROTO=dhcp4
                STARTMODE=auto
            """
            ),
        }
        self._apply_and_verify(
            self.distro.apply_network_config,
            V1_NET_CFG_IPV6,
            expected_cfgs=expected_cfgs.copy(),
        )


class TestNetCfgDistroArch(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroArch, self).setUp()
        self.distro = self._get_distro("arch", renderers=["netplan"])

    def _apply_and_verify(
        self,
        apply_fn,
        config,
        expected_cfgs=None,
        bringup=False,
        with_netplan=False,
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch(
            "cloudinit.net.netplan.available", return_value=with_netplan
        ):
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        mode = 0o600 if with_netplan else 0o644
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(expected, results[cfgpath])
            self.assertEqual(mode, get_mode(cfgpath, tmpd))

    def netctl_path(self, iface):
        return "/etc/netctl/%s" % iface

    def netplan_path(self):
        return "/etc/netplan/50-cloud-init.yaml"

    def test_apply_network_config_v1_with_netplan(self):
        expected_cfgs = {
            self.netplan_path(): dedent(
                """\
                # generated by cloud-init
                network:
                    version: 2
                    ethernets:
                        eth0:
                            addresses:
                            - 192.168.1.5/24
                            routes:
                            -   to: default
                                via: 192.168.1.254
                        eth1:
                            dhcp4: true
                """
            ),
        }

        with mock.patch(
            "cloudinit.net.netplan.get_devicelist", return_value=[]
        ):
            self._apply_and_verify(
                self.distro.apply_network_config,
                V1_NET_CFG,
                expected_cfgs=expected_cfgs.copy(),
                with_netplan=True,
            )


class TestNetCfgDistroPhoton(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroPhoton, self).setUp()
        self.distro = self._get_distro("photon", renderers=["networkd"])

    def create_conf_dict(self, contents):
        content_dict = {}
        for line in contents:
            if line:
                line = line.strip()
                if line and re.search(r"^\[(.+)\]$", line):
                    content_dict[line] = []
                    key = line
                elif line:
                    assert key
                    content_dict[key].append(line)

        return content_dict

    def compare_dicts(self, actual, expected):
        for k, v in actual.items():
            self.assertEqual(sorted(expected[k]), sorted(v))

    def _apply_and_verify(
        self, apply_fn, config, expected_cfgs=None, bringup=False
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.networkd.available") as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            actual = self.create_conf_dict(results[cfgpath].splitlines())
            self.compare_dicts(actual, expected)
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def nwk_file_path(self, ifname):
        return "/etc/systemd/network/10-cloud-init-%s.network" % ifname

    def net_cfg_1(self, ifname):
        ret = (
            """\
        [Match]
        Name=%s
        [Network]
        DHCP=no
        [Address]
        Address=192.168.1.5/24
        [Route]
        Gateway=192.168.1.254"""
            % ifname
        )
        return ret

    def net_cfg_2(self, ifname):
        ret = (
            """\
        [Match]
        Name=%s
        [Network]
        DHCP=ipv4"""
            % ifname
        )
        return ret

    def test_photon_network_config_v1(self):
        tmp = self.net_cfg_1("eth0").splitlines()
        expected_eth0 = self.create_conf_dict(tmp)

        tmp = self.net_cfg_2("eth1").splitlines()
        expected_eth1 = self.create_conf_dict(tmp)

        expected_cfgs = {
            self.nwk_file_path("eth0"): expected_eth0,
            self.nwk_file_path("eth1"): expected_eth1,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, V1_NET_CFG, expected_cfgs.copy()
        )

    def test_photon_network_config_v2(self):
        tmp = self.net_cfg_1("eth7").splitlines()
        expected_eth7 = self.create_conf_dict(tmp)

        tmp = self.net_cfg_2("eth9").splitlines()
        expected_eth9 = self.create_conf_dict(tmp)

        expected_cfgs = {
            self.nwk_file_path("eth7"): expected_eth7,
            self.nwk_file_path("eth9"): expected_eth9,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, V2_NET_CFG, expected_cfgs.copy()
        )

    def test_photon_network_config_v1_with_duplicates(self):
        expected = """\
        [Match]
        Name=eth0
        [Network]
        DHCP=no
        DNS=1.2.3.4
        Domains=test.com
        [Address]
        Address=192.168.0.102/24"""

        net_cfg = safeyaml.load(V1_NET_CFG_WITH_DUPS)

        expected = self.create_conf_dict(expected.splitlines())
        expected_cfgs = {
            self.nwk_file_path("eth0"): expected,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, net_cfg, expected_cfgs.copy()
        )


class TestNetCfgDistroMariner(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroMariner, self).setUp()
        self.distro = self._get_distro("mariner", renderers=["networkd"])

    def create_conf_dict(self, contents):
        content_dict = {}
        for line in contents:
            if line:
                line = line.strip()
                if line and re.search(r"^\[(.+)\]$", line):
                    content_dict[line] = []
                    key = line
                elif line:
                    assert key
                    content_dict[key].append(line)

        return content_dict

    def compare_dicts(self, actual, expected):
        for k, v in actual.items():
            self.assertEqual(sorted(expected[k]), sorted(v))

    def _apply_and_verify(
        self, apply_fn, config, expected_cfgs=None, bringup=False
    ):
        if not expected_cfgs:
            raise ValueError("expected_cfg must not be None")

        tmpd = None
        with mock.patch("cloudinit.net.networkd.available") as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            actual = self.create_conf_dict(results[cfgpath].splitlines())
            self.compare_dicts(actual, expected)
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def nwk_file_path(self, ifname):
        return "/etc/systemd/network/10-cloud-init-%s.network" % ifname

    def net_cfg_1(self, ifname):
        ret = (
            """\
        [Match]
        Name=%s
        [Network]
        DHCP=no
        [Address]
        Address=192.168.1.5/24
        [Route]
        Gateway=192.168.1.254"""
            % ifname
        )
        return ret

    def net_cfg_2(self, ifname):
        ret = (
            """\
        [Match]
        Name=%s
        [Network]
        DHCP=ipv4"""
            % ifname
        )
        return ret

    def test_mariner_network_config_v1(self):
        tmp = self.net_cfg_1("eth0").splitlines()
        expected_eth0 = self.create_conf_dict(tmp)

        tmp = self.net_cfg_2("eth1").splitlines()
        expected_eth1 = self.create_conf_dict(tmp)

        expected_cfgs = {
            self.nwk_file_path("eth0"): expected_eth0,
            self.nwk_file_path("eth1"): expected_eth1,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, V1_NET_CFG, expected_cfgs.copy()
        )

    def test_mariner_network_config_v2(self):
        tmp = self.net_cfg_1("eth7").splitlines()
        expected_eth7 = self.create_conf_dict(tmp)

        tmp = self.net_cfg_2("eth9").splitlines()
        expected_eth9 = self.create_conf_dict(tmp)

        expected_cfgs = {
            self.nwk_file_path("eth7"): expected_eth7,
            self.nwk_file_path("eth9"): expected_eth9,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, V2_NET_CFG, expected_cfgs.copy()
        )

    def test_mariner_network_config_v1_with_duplicates(self):
        expected = """\
        [Match]
        Name=eth0
        [Network]
        DHCP=no
        DNS=1.2.3.4
        Domains=test.com
        [Address]
        Address=192.168.0.102/24"""

        net_cfg = safeyaml.load(V1_NET_CFG_WITH_DUPS)

        expected = self.create_conf_dict(expected.splitlines())
        expected_cfgs = {
            self.nwk_file_path("eth0"): expected,
        }

        self._apply_and_verify(
            self.distro.apply_network_config, net_cfg, expected_cfgs.copy()
        )


def get_mode(path, target=None):
    # Mask upper st_mode bits like S_IFREG bit preserve sticky and isuid/osgid
    return os.stat(subp.target_path(target, path)).st_mode & 0o777
