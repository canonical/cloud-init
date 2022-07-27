# This file is part of cloud-init. See LICENSE file for license information.
import re
from copy import deepcopy
from unittest import mock

import pytest

from cloudinit.config import cc_lxd
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud


class TestLxd(t_help.CiTestCase):

    with_logs = True

    lxd_cfg = {
        "lxd": {
            "init": {
                "network_address": "0.0.0.0",
                "storage_backend": "zfs",
                "storage_pool": "poolname",
            }
        }
    }
    backend_def = (
        ("zfs", "zfs", "zfsutils-linux"),
        ("btrfs", "mkfs.btrfs", "btrfs-progs"),
        ("lvm", "lvcreate", "lvm2"),
        ("dir", None, None),
    )

    @mock.patch("cloudinit.config.cc_lxd.subp.subp", return_value=True)
    @mock.patch("cloudinit.config.cc_lxd.subp.which", return_value=False)
    @mock.patch(
        "cloudinit.config.cc_lxd.maybe_cleanup_default", return_value=None
    )
    def test_lxd_init(self, m_maybe_clean, m_which, m_subp):
        cc = get_cloud(mocked_distro=True)
        m_install = cc.distro.install_packages

        for backend, cmd, package in self.backend_def:
            lxd_cfg = deepcopy(self.lxd_cfg)
            lxd_cfg["lxd"]["init"]["storage_backend"] = backend
            m_subp.call_args_list = []
            m_install.call_args_list = []
            cc_lxd.handle("cc_lxd", lxd_cfg, cc, self.logger, [])
            if cmd:
                m_which.assert_called_with(cmd)
            # no bridge config, so maybe_cleanup should not be called.
            self.assertFalse(m_maybe_clean.called)
            self.assertEqual(
                [
                    mock.call(list(filter(None, ["lxd", package]))),
                ],
                m_install.call_args_list,
            )
            self.assertEqual(
                [
                    mock.call(["lxd", "waitready", "--timeout=300"]),
                    mock.call(
                        [
                            "lxd",
                            "init",
                            "--auto",
                            "--network-address=0.0.0.0",
                            f"--storage-backend={backend}",
                            "--storage-pool=poolname",
                        ]
                    ),
                ],
                m_subp.call_args_list,
            )

    @mock.patch("cloudinit.config.cc_lxd.subp.which", return_value=False)
    def test_lxd_package_install(self, m_which):
        for backend, _, package in self.backend_def:
            lxd_cfg = deepcopy(self.lxd_cfg)
            lxd_cfg["lxd"]["init"]["storage_backend"] = backend

            packages = cc_lxd.get_required_packages(lxd_cfg["lxd"]["init"])
            assert "lxd" in packages
            if package:
                assert package in packages

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_lxd_install(self, mock_subp, m_maybe_clean):
        cc = get_cloud()
        cc.distro = mock.MagicMock()
        mock_subp.which.return_value = None
        cc_lxd.handle("cc_lxd", self.lxd_cfg, cc, self.logger, [])
        self.assertNotIn("WARN", self.logs.getvalue())
        self.assertTrue(cc.distro.install_packages.called)
        cc_lxd.handle("cc_lxd", self.lxd_cfg, cc, self.logger, [])
        self.assertFalse(m_maybe_clean.called)
        install_pkg = cc.distro.install_packages.call_args_list[0][0][0]
        self.assertEqual(sorted(install_pkg), ["lxd", "zfsutils-linux"])

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_no_init_does_nothing(self, mock_subp, m_maybe_clean):
        cc = get_cloud()
        cc.distro = mock.MagicMock()
        cc_lxd.handle("cc_lxd", {"lxd": {}}, cc, self.logger, [])
        self.assertFalse(cc.distro.install_packages.called)
        self.assertFalse(mock_subp.subp.called)
        self.assertFalse(m_maybe_clean.called)

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_no_lxd_does_nothing(self, mock_subp, m_maybe_clean):
        cc = get_cloud()
        cc.distro = mock.MagicMock()
        cc_lxd.handle("cc_lxd", {"package_update": True}, cc, self.logger, [])
        self.assertFalse(cc.distro.install_packages.called)
        self.assertFalse(mock_subp.subp.called)
        self.assertFalse(m_maybe_clean.called)

    def test_lxd_debconf_new_full(self):
        data = {
            "mode": "new",
            "name": "testbr0",
            "ipv4_address": "10.0.8.1",
            "ipv4_netmask": "24",
            "ipv4_dhcp_first": "10.0.8.2",
            "ipv4_dhcp_last": "10.0.8.254",
            "ipv4_dhcp_leases": "250",
            "ipv4_nat": "true",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
            "domain": "lxd",
        }
        self.assertEqual(
            cc_lxd.bridge_to_debconf(data),
            {
                "lxd/setup-bridge": "true",
                "lxd/bridge-name": "testbr0",
                "lxd/bridge-ipv4": "true",
                "lxd/bridge-ipv4-address": "10.0.8.1",
                "lxd/bridge-ipv4-netmask": "24",
                "lxd/bridge-ipv4-dhcp-first": "10.0.8.2",
                "lxd/bridge-ipv4-dhcp-last": "10.0.8.254",
                "lxd/bridge-ipv4-dhcp-leases": "250",
                "lxd/bridge-ipv4-nat": "true",
                "lxd/bridge-ipv6": "true",
                "lxd/bridge-ipv6-address": "fd98:9e0:3744::1",
                "lxd/bridge-ipv6-netmask": "64",
                "lxd/bridge-ipv6-nat": "true",
                "lxd/bridge-domain": "lxd",
            },
        )

    def test_lxd_debconf_new_partial(self):
        data = {
            "mode": "new",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
        }
        self.assertEqual(
            cc_lxd.bridge_to_debconf(data),
            {
                "lxd/setup-bridge": "true",
                "lxd/bridge-ipv6": "true",
                "lxd/bridge-ipv6-address": "fd98:9e0:3744::1",
                "lxd/bridge-ipv6-netmask": "64",
                "lxd/bridge-ipv6-nat": "true",
            },
        )

    def test_lxd_debconf_existing(self):
        data = {"mode": "existing", "name": "testbr0"}
        self.assertEqual(
            cc_lxd.bridge_to_debconf(data),
            {
                "lxd/setup-bridge": "false",
                "lxd/use-existing-bridge": "true",
                "lxd/bridge-name": "testbr0",
            },
        )

    def test_lxd_debconf_none(self):
        data = {"mode": "none"}
        self.assertEqual(
            cc_lxd.bridge_to_debconf(data),
            {"lxd/setup-bridge": "false", "lxd/bridge-name": ""},
        )

    def test_lxd_cmd_new_full(self):
        data = {
            "mode": "new",
            "name": "testbr0",
            "ipv4_address": "10.0.8.1",
            "ipv4_netmask": "24",
            "ipv4_dhcp_first": "10.0.8.2",
            "ipv4_dhcp_last": "10.0.8.254",
            "ipv4_dhcp_leases": "250",
            "ipv4_nat": "true",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
            "domain": "lxd",
            "mtu": 9000,
        }
        self.assertEqual(
            cc_lxd.bridge_to_cmd(data),
            (
                [
                    "network",
                    "create",
                    "testbr0",
                    "ipv4.address=10.0.8.1/24",
                    "ipv4.nat=true",
                    "ipv4.dhcp.ranges=10.0.8.2-10.0.8.254",
                    "ipv6.address=fd98:9e0:3744::1/64",
                    "ipv6.nat=true",
                    "dns.domain=lxd",
                    "bridge.mtu=9000",
                ],
                ["network", "attach-profile", "testbr0", "default", "eth0"],
            ),
        )

    def test_lxd_cmd_new_partial(self):
        data = {
            "mode": "new",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
            "mtu": -1,
        }
        self.assertEqual(
            cc_lxd.bridge_to_cmd(data),
            (
                [
                    "network",
                    "create",
                    "lxdbr0",
                    "ipv4.address=none",
                    "ipv6.address=fd98:9e0:3744::1/64",
                    "ipv6.nat=true",
                ],
                ["network", "attach-profile", "lxdbr0", "default", "eth0"],
            ),
        )

    def test_lxd_cmd_existing(self):
        data = {"mode": "existing", "name": "testbr0"}
        self.assertEqual(
            cc_lxd.bridge_to_cmd(data),
            (
                None,
                ["network", "attach-profile", "testbr0", "default", "eth0"],
            ),
        )

    def test_lxd_cmd_none(self):
        data = {"mode": "none"}
        self.assertEqual(cc_lxd.bridge_to_cmd(data), (None, None))


class TestLxdMaybeCleanupDefault(t_help.CiTestCase):
    """Test the implementation of maybe_cleanup_default."""

    defnet = cc_lxd._DEFAULT_NETWORK_NAME

    @mock.patch("cloudinit.config.cc_lxd._lxc")
    def test_network_other_than_default_not_deleted(self, m_lxc):
        """deletion or removal should only occur if bridge is default."""
        cc_lxd.maybe_cleanup_default(
            net_name="lxdbr1", did_init=True, create=True, attach=True
        )
        m_lxc.assert_not_called()

    @mock.patch("cloudinit.config.cc_lxd._lxc")
    def test_did_init_false_does_not_delete(self, m_lxc):
        """deletion or removal should only occur if did_init is True."""
        cc_lxd.maybe_cleanup_default(
            net_name=self.defnet, did_init=False, create=True, attach=True
        )
        m_lxc.assert_not_called()

    @mock.patch("cloudinit.config.cc_lxd._lxc")
    def test_network_deleted_if_create_true(self, m_lxc):
        """deletion of network should occur if create is True."""
        cc_lxd.maybe_cleanup_default(
            net_name=self.defnet, did_init=True, create=True, attach=False
        )
        m_lxc.assert_called_with(["network", "delete", self.defnet])

    @mock.patch("cloudinit.config.cc_lxd._lxc")
    def test_device_removed_if_attach_true(self, m_lxc):
        """deletion of network should occur if create is True."""
        nic_name = "my_nic"
        profile = "my_profile"
        cc_lxd.maybe_cleanup_default(
            net_name=self.defnet,
            did_init=True,
            create=False,
            attach=True,
            profile=profile,
            nic_name=nic_name,
        )
        m_lxc.assert_called_once_with(
            ["profile", "device", "remove", profile, nic_name]
        )


class TestLXDSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Only allow init and bridge keys
            ({"lxd": {"bridgeo": 1}}, "Additional properties are not allowed"),
            # Only allow init.storage_backend values zfs and dir
            (
                {"lxd": {"init": {"storage_backend": "1zfs"}}},
                re.escape("not one of ['zfs', 'dir', 'lvm', 'btrfs']"),
            ),
            ({"lxd": {"init": {"storage_backend": "lvm"}}}, None),
            ({"lxd": {"init": {"storage_backend": "btrfs"}}}, None),
            ({"lxd": {"init": {"storage_backend": "zfs"}}}, None),
            # Require bridge.mode
            ({"lxd": {"bridge": {}}}, "bridge: 'mode' is a required property"),
            # Require init or bridge keys
            ({"lxd": {}}, "does not have enough properties"),
            # Require bridge.mode
            ({"lxd": {"bridge": {"mode": "new", "mtu": 9000}}}, None),
            # LXD's default value
            ({"lxd": {"bridge": {"mode": "new", "mtu": -1}}}, None),
            # No additionalProperties
            (
                {"lxd": {"init": {"invalid": None}}},
                "Additional properties are not allowed",
            ),
            (
                {"lxd": {"bridge": {"mode": None, "garbage": None}}},
                "Additional properties are not allowed",
            ),
        ],
    )
    @t_help.skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            validate_cloudconfig_schema(config, get_schema(), strict=True)


# vi: ts=4 expandtab
