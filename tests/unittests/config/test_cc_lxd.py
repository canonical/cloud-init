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
from cloudinit.helpers import Paths
from cloudinit.subp import ProcessExecutionError
from cloudinit.util import del_file
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud

BACKEND_DEF = (
    ("zfs", "zfs", "zfsutils-linux"),
    ("btrfs", "mkfs.btrfs", "btrfs-progs"),
    ("lvm", "lvcreate", "lvm2"),
    ("dir", None, None),
)
LXD_INIT_CFG = {
    "lxd": {
        "init": {
            "network_address": "0.0.0.0",
            "storage_backend": "zfs",
            "storage_pool": "poolname",
        }
    }
}


class TestLxd:
    @mock.patch("cloudinit.config.cc_lxd.util.system_info")
    @mock.patch("cloudinit.config.cc_lxd.os.path.exists", return_value=True)
    @mock.patch("cloudinit.config.cc_lxd.subp.subp")
    @mock.patch("cloudinit.config.cc_lxd.subp.which", return_value=False)
    @mock.patch(
        "cloudinit.config.cc_lxd.maybe_cleanup_default", return_value=None
    )
    def test_lxd_init(
        self, maybe_clean, which, subp, exists, system_info, tmpdir
    ):
        def my_subp(*args, **kwargs):
            if args[0] == ["snap", "list", "lxd"]:
                raise ProcessExecutionError(
                    stderr="error: no matching snaps installed",
                    exit_code=1,
                )
            return ("", "")

        subp.side_effect = my_subp
        system_info.return_value = {"uname": [0, 1, "mykernel"]}
        sem_file = f"{tmpdir}/sem/snap_seeded.once"
        cc = get_cloud(mocked_distro=True, paths=Paths({"cloud_dir": tmpdir}))
        install = cc.distro.install_packages

        for backend, cmd, package in BACKEND_DEF:
            lxd_cfg = deepcopy(LXD_INIT_CFG)
            lxd_cfg["lxd"]["init"]["storage_backend"] = backend
            subp.call_args_list = []
            install.call_args_list = []
            exists.call_args_list = []
            cc_lxd.handle("cc_lxd", lxd_cfg, cc, [])
            if cmd:
                which.assert_called_with(cmd)
            # no bridge config, so maybe_cleanup should not be called.
            assert not maybe_clean.called
            if package:
                assert [mock.call([package])] == install.call_args_list
            assert [
                mock.call(["snap", "list", "lxd"]),
                mock.call(["snap", "install", "lxd"]),
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
            ] == subp.call_args_list

            assert [mock.call(sem_file)] == exists.call_args_list
            del_file(sem_file)

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    @mock.patch("cloudinit.config.cc_lxd.subp.which", return_value=False)
    def test_lxd_install(
        self, m_which, mock_subp, m_maybe_clean, tmpdir, caplog
    ):
        cc = get_cloud(paths=Paths({"cloud_dir": tmpdir}))
        cc.distro = mock.MagicMock()
        mock_subp.which.return_value = None
        cc_lxd.handle("cc_lxd", LXD_INIT_CFG, cc, [])
        assert "WARN" not in caplog.text
        assert cc.distro.install_packages.called
        cc_lxd.handle("cc_lxd", LXD_INIT_CFG, cc, [])
        assert not m_maybe_clean.called
        install_pkg = cc.distro.install_packages.call_args_list[0][0][0]
        assert sorted(install_pkg) == ["zfsutils-linux"]

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_no_init_does_nothing(self, mock_subp, m_maybe_clean, tmpdir):
        cc = get_cloud(paths=Paths({"cloud_dir": tmpdir}))
        cc.distro = mock.MagicMock()
        cc_lxd.handle("cc_lxd", {"lxd": {}}, cc, [])
        assert not cc.distro.install_packages.called
        assert not mock_subp.subp.called
        assert not m_maybe_clean.called

    @mock.patch("cloudinit.config.cc_lxd.maybe_cleanup_default")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_no_lxd_does_nothing(self, mock_subp, m_maybe_clean, tmpdir):
        cc = get_cloud(paths=Paths({"cloud_dir": tmpdir}))
        cc.distro = mock.MagicMock()
        cc_lxd.handle("cc_lxd", {"package_update": True}, cc, [])
        assert not cc.distro.install_packages.called
        assert not mock_subp.subp.called
        assert not m_maybe_clean.called

    @mock.patch("cloudinit.config.cc_lxd.util.wait_for_snap_seeded")
    @mock.patch("cloudinit.config.cc_lxd.subp")
    def test_lxd_preseed(self, mock_subp, wait_for_snap_seeded, tmpdir):
        cc = get_cloud(paths=Paths({"cloud_dir": tmpdir}))
        cc.distro = mock.MagicMock()
        cc_lxd.handle(
            "cc_lxd",
            {"lxd": {"preseed": '{"chad": True}'}},
            cc,
            [],
        )
        assert [
            mock.call(["snap", "list", "lxd"]),
            mock.call(["lxd", "waitready", "--timeout=300"]),
            mock.call(["lxd", "init", "--preseed"], data='{"chad": True}'),
        ] == mock_subp.subp.call_args_list
        wait_for_snap_seeded.assert_called_once_with(cc)

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
        assert cc_lxd.bridge_to_debconf(data) == {
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
        }

    def test_lxd_debconf_new_partial(self):
        data = {
            "mode": "new",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
        }
        assert cc_lxd.bridge_to_debconf(data) == {
            "lxd/setup-bridge": "true",
            "lxd/bridge-ipv6": "true",
            "lxd/bridge-ipv6-address": "fd98:9e0:3744::1",
            "lxd/bridge-ipv6-netmask": "64",
            "lxd/bridge-ipv6-nat": "true",
        }

    def test_lxd_debconf_existing(self):
        data = {"mode": "existing", "name": "testbr0"}
        assert cc_lxd.bridge_to_debconf(data) == {
            "lxd/setup-bridge": "false",
            "lxd/use-existing-bridge": "true",
            "lxd/bridge-name": "testbr0",
        }

    def test_lxd_debconf_none(self):
        data = {"mode": "none"}
        assert cc_lxd.bridge_to_debconf(data) == {
            "lxd/setup-bridge": "false",
            "lxd/bridge-name": "",
        }

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
        assert cc_lxd.bridge_to_cmd(data) == (
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
        )

    def test_lxd_cmd_new_partial(self):
        data = {
            "mode": "new",
            "ipv6_address": "fd98:9e0:3744::1",
            "ipv6_netmask": "64",
            "ipv6_nat": "true",
            "mtu": -1,
        }
        assert cc_lxd.bridge_to_cmd(data) == (
            [
                "network",
                "create",
                "lxdbr0",
                "ipv4.address=none",
                "ipv6.address=fd98:9e0:3744::1/64",
                "ipv6.nat=true",
            ],
            ["network", "attach-profile", "lxdbr0", "default", "eth0"],
        )

    def test_lxd_cmd_existing(self):
        data = {"mode": "existing", "name": "testbr0"}
        assert cc_lxd.bridge_to_cmd(data) == (
            None,
            ["network", "attach-profile", "testbr0", "default", "eth0"],
        )

    def test_lxd_cmd_none(self):
        data = {"mode": "none"}
        assert cc_lxd.bridge_to_cmd(data) == (None, None)

    def test_no_thinpool(self, mocker, caplog):
        def my_subp(*args, **kwargs):
            if args[0] == ["lxd", "init", "--auto", "--storage-backend=lvm"]:
                raise ProcessExecutionError(
                    stderr='Error: Failed to create storage pool "default"',
                    exit_code=1,
                )
            return ("", "")

        m_subp = mocker.patch(
            "cloudinit.config.cc_lxd.subp.subp",
            side_effect=my_subp,
        )
        cc_lxd.handle_init_cfg({"storage_backend": "lvm"})
        assert "Cloud-init doesn't use thinpool" in caplog.text
        assert (
            mock.call(
                [
                    "lxc",
                    "storage",
                    "create",
                    "default",
                    "lvm",
                    "lvm.use_thinpool=false",
                ]
            )
            in m_subp.call_args_list
        )
        assert mock.call(["lxd", "init", "--auto"]) in m_subp.call_args_list


class TestLxdMaybeCleanupDefault:
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


class TestGetRequiredPackages:
    @pytest.mark.parametrize(
        "storage_type, cmd, preseed, package",
        (
            ("zfs", "zfs", "", "zfsutils-linux"),
            ("btrfs", "mkfs.btrfs", "", "btrfs-progs"),
            ("lvm", "lvcreate", "", "lvm2"),
            ("lvm", "lvcreate", "storage_pools: [{driver: lvm}]", "lvm2"),
            ("dir", None, "", None),
        ),
    )
    @mock.patch("cloudinit.config.cc_lxd.subp.which", return_value=False)
    def test_lxd_package_install(
        self, m_which, storage_type, cmd, preseed, package
    ):
        if preseed:  # preseed & lxd.init mutually exclusive
            init_cfg = {}
        else:
            lxd_cfg = deepcopy(LXD_INIT_CFG)
            lxd_cfg["lxd"]["init"]["storage_backend"] = storage_type
            init_cfg = lxd_cfg["lxd"]["init"]

        packages = cc_lxd.get_required_packages(init_cfg, preseed)
        which_calls = []
        if package:
            which_calls.append(mock.call(cmd))
            assert package in packages
        assert which_calls == m_which.call_args_list


class TestLXDSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Only allow init, bridge and preseed keys
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
            ({"lxd": {}}, f"lxd: {{}} {t_help.SCHEMA_EMPTY_ERROR}"),
            # Require some non-empty preseed config of type string
            ({"lxd": {"preseed": {}}}, "not of type 'string'"),
            ({"lxd": {"preseed": ""}}, None),
            ({"lxd": {"preseed": "this is {} opaque"}}, None),
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

    @pytest.mark.parametrize(
        "init_cfg, bridge_cfg, preseed_str, error_expectation",
        (
            pytest.param(
                {}, {}, "", t_help.does_not_raise(), id="empty_cfgs_no_errors"
            ),
            pytest.param(
                {"init-cfg": 1},
                {"bridge-cfg": 2},
                "",
                t_help.does_not_raise(),
                id="cfg_init_and_bridge_allowed",
            ),
            pytest.param(
                {},
                {},
                "profiles: []",
                t_help.does_not_raise(),
                id="cfg_preseed_allowed_without_bridge_or_init",
            ),
            pytest.param(
                {"init-cfg": 1},
                {"bridge-cfg": 2},
                "profiles: []",
                pytest.raises(
                    ValueError,
                    match=re.escape(
                        "Unable to configure LXD. lxd.preseed config can not"
                        " be provided with key(s): lxd.init, lxd.bridge"
                    ),
                ),
            ),
            pytest.param(
                "nope",
                {},
                "",
                pytest.raises(
                    ValueError,
                    match=re.escape(
                        "lxd.init config must be a dictionary. found a 'str'"
                    ),
                ),
            ),
        ),
    )
    def test_supplemental_schema_validation_raises_value_error(
        self, init_cfg, bridge_cfg, preseed_str, error_expectation
    ):
        """LXD is strict on invalid user-data raising conspicuous ValueErrors
        cc_lxd.supplemental_schema_validation

        Hard errors result is faster triage/awareness of config problems than
        warnings do.
        """
        with error_expectation:
            cc_lxd.supplemental_schema_validation(
                init_cfg, bridge_cfg, preseed_str
            )
