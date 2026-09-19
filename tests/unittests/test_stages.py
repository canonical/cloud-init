# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

"""Tests related to cloudinit.stages module."""

import json
import os
import stat
from unittest import mock

import pytest

from cloudinit import sources, stages
from cloudinit.event import EventScope, EventType
from cloudinit.helpers import Paths
from cloudinit.sources import DataSource, NetworkConfigSource
from cloudinit.util import sym_link, write_file
from tests.unittests.util import TEST_INSTANCE_ID, FakeDataSource

M_PATH = "cloudinit.stages."


class TestUpdateEventEnabled:
    @pytest.mark.parametrize(
        "cfg",
        [
            {},
            {"updates": {}},
            {"updates": {"when": ["boot"]}},
            {"updates": {"when": ["hotplug"]}},
            {"updates": {"when": ["boot", "hotplug"]}},
        ],
    )
    @pytest.mark.parametrize(
        ["enabled_file_content", "enabled"],
        [
            ({"scopes": ["network"]}, True),
            ({"scopes": []}, False),
        ],
    )
    @mock.patch(M_PATH + "util.read_hotplug_enabled_file")
    def test_hotplug_added_by_file(
        self, m_read_hotplug_enabled_file, cfg, enabled_file_content, enabled
    ):
        m_datasource = mock.MagicMock(spec=DataSource)
        m_datasource.paths = mock.MagicMock(spec=Paths)
        m_datasource.default_update_events = {}
        m_datasource.supported_update_events = {
            EventScope.NETWORK: [EventType.HOTPLUG]
        }
        m_read_hotplug_enabled_file.return_value = enabled_file_content
        cfg = {}
        assert enabled is stages.update_event_enabled(
            m_datasource, cfg, EventType.HOTPLUG, EventScope.NETWORK
        )


class TestNetworkConfigWithoutDS:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir):
        self.tmpdir = tmpdir
        self.init = stages.Init()
        self.init._cfg = {
            "system_info": {
                "distro": "ubuntu",
                "paths": {"cloud_dir": self.tmpdir, "run_dir": self.tmpdir},
            }
        }
        tmpdir.mkdir("instance-uuid")
        sym_link(tmpdir.join("instance-uuid"), tmpdir.join("instance"))

    @mock.patch(
        M_PATH + "cmdline.read_initramfs_config",
        return_value={"config": "disabled"},
    )
    @mock.patch(
        M_PATH + "cmdline.read_kernel_cmdline_config",
        return_value={"config": "disabled"},
    )
    def test_network_config(self, m_cmdline, m_initramfs):
        self.init.apply_network_config(False)


class TestInit:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir):
        self.tmpdir = tmpdir
        self.init = stages.Init()
        self.init._cfg = {
            "system_info": {
                "distro": "ubuntu",
                "paths": {"cloud_dir": self.tmpdir, "run_dir": self.tmpdir},
            }
        }
        tmpdir.mkdir("instance-uuid")
        sym_link(tmpdir.join("instance-uuid"), tmpdir.join("instance"))
        self.init.datasource = FakeDataSource(paths=self.init.paths)
        self._real_is_new_instance = self.init.is_new_instance
        self.init.is_new_instance = mock.Mock(return_value=True)

    def test_wb__find_networking_config_disabled(self):
        """find_networking_config returns no config when disabled."""
        disable_file = os.path.join(
            self.init.paths.get_cpath("data"), "upgraded-network"
        )
        write_file(disable_file, "")
        assert (None, disable_file) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "net_config",
        [
            {"config": "disabled"},
            {"network": {"config": "disabled"}},
        ],
    )
    def test_wb__find_networking_config_disabled_by_kernel(
        self, m_cmdline, m_initramfs, net_config, caplog
    ):
        """find_networking_config returns when disabled by kernel cmdline."""
        m_cmdline.return_value = net_config
        m_initramfs.return_value = {"config": ["fake_initrd"]}
        assert (
            None,
            NetworkConfigSource.CMD_LINE,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "DEBUG"
        assert "network config disabled by cmdline" in caplog.text

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "net_config",
        [
            {"config": "disabled"},
            {"network": {"config": "disabled"}},
        ],
    )
    def test_wb__find_networking_config_disabled_by_initrd(
        self, m_cmdline, m_initramfs, net_config, caplog
    ):
        """find_networking_config returns when disabled by kernel cmdline."""
        m_cmdline.return_value = {}
        m_initramfs.return_value = net_config
        assert (
            None,
            NetworkConfigSource.INITRAMFS,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "DEBUG"
        assert "network config disabled by initramfs" in caplog.text

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "net_config",
        [
            {"config": "disabled"},
            {"network": {"config": "disabled"}},
        ],
    )
    def test_wb__find_networking_config_disabled_by_datasrc(
        self, m_cmdline, m_initramfs, net_config, caplog
    ):
        """find_networking_config returns when disabled by datasource cfg."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        m_initramfs.return_value = {}  # initramfs doesn't disable networking
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": {},
        }  # system config doesn't disable

        self.init.datasource = FakeDataSource(network_config=net_config)
        assert (
            None,
            NetworkConfigSource.DS,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "DEBUG"
        assert "network config disabled by ds" in caplog.text

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "net_config",
        [
            {"config": "disabled"},
            {"network": {"config": "disabled"}},
        ],
    )
    def test_wb__find_networking_config_disabled_by_sysconfig(
        self, m_cmdline, m_initramfs, net_config, caplog
    ):
        """find_networking_config returns when disabled by system config."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        m_initramfs.return_value = {}  # initramfs doesn't disable networking
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": net_config,
        }
        assert (
            None,
            NetworkConfigSource.SYSTEM_CFG,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "DEBUG"
        assert "network config disabled by system_cfg" in caplog.text

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test__find_networking_config_uses_datasrc_order(
        self, m_cmdline, m_initramfs, in_config, out_config
    ):
        """find_networking_config should check sources in DS defined order"""
        # cmdline and initramfs, which would normally be preferred over other
        # sources, disable networking; in this case, though, the DS moves them
        # later so its own config is preferred
        m_cmdline.return_value = {"config": "disabled"}
        m_initramfs.return_value = {"config": "disabled"}

        self.init.datasource = FakeDataSource(network_config=in_config)
        self.init.datasource.network_config_sources = [
            NetworkConfigSource.DS,
            NetworkConfigSource.SYSTEM_CFG,
            NetworkConfigSource.CMD_LINE,
            NetworkConfigSource.INITRAMFS,
        ]

        assert (
            out_config,
            NetworkConfigSource.DS,
        ) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test__find_networking_config_warns_if_datasrc_uses_invalid_src(
        self, m_cmdline, m_initramfs, in_config, out_config, caplog
    ):
        """find_networking_config should check sources in DS defined order"""
        self.init.datasource = FakeDataSource(network_config=in_config)
        self.init.datasource.network_config_sources = [
            "invalid_src",
            NetworkConfigSource.DS,
        ]

        assert (
            out_config,
            NetworkConfigSource.DS,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "WARNING"
        assert (
            "data source specifies an invalid network cfg_source: invalid_src"
            in caplog.text
        )

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test__find_networking_config_warns_if_datasrc_uses_unavailable_src(
        self, m_cmdline, m_initramfs, in_config, out_config, caplog
    ):
        """find_networking_config should check sources in DS defined order"""
        self.init.datasource = FakeDataSource(network_config=in_config)
        self.init.datasource.network_config_sources = [
            NetworkConfigSource.FALLBACK,
            NetworkConfigSource.DS,
        ]

        assert (
            out_config,
            NetworkConfigSource.DS,
        ) == self.init._find_networking_config()
        assert caplog.records[0].levelname == "WARNING"
        assert (
            "data source specifies an unavailable network cfg_source: fallback"
            in caplog.text
        )

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test_wb__find_networking_config_returns_kernel(
        self, m_cmdline, m_initramfs, in_config, out_config
    ):
        """find_networking_config returns kernel cmdline config if present."""
        m_cmdline.return_value = in_config
        m_initramfs.return_value = {"config": ["fake_initrd"]}
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": {"config": ["fakesys_config"]},
        }
        self.init.datasource = FakeDataSource(
            network_config={"config": ["fakedatasource"]}
        )
        assert (
            out_config,
            NetworkConfigSource.CMD_LINE,
        ) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test_wb__find_networking_config_returns_initramfs(
        self, m_cmdline, m_initramfs, in_config, out_config
    ):
        """find_networking_config returns initramfs config if present."""
        m_cmdline.return_value = {}
        m_initramfs.return_value = in_config
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": {"config": ["fakesys_config"]},
        }
        self.init.datasource = FakeDataSource(
            network_config={"config": ["fakedatasource"]}
        )
        assert (
            out_config,
            NetworkConfigSource.INITRAMFS,
        ) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test_wb__find_networking_config_returns_system_cfg(
        self, m_cmdline, m_initramfs, in_config, out_config
    ):
        """find_networking_config returns system config when present."""
        m_cmdline.return_value = {}  # No kernel network config
        m_initramfs.return_value = {}  # no initramfs network config
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": in_config,
        }
        self.init.datasource = FakeDataSource(
            network_config={"config": ["fakedatasource"]}
        )
        assert (
            out_config,
            NetworkConfigSource.SYSTEM_CFG,
        ) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    @pytest.mark.parametrize(
        "in_config,out_config",
        [
            ({"config": {"a": True}}, {"config": {"a": True}}),
            ({"network": {"config": {"a": True}}}, {"config": {"a": True}}),
        ],
    )
    def test_wb__find_networking_config_returns_datasrc_cfg(
        self, m_cmdline, m_initramfs, in_config, out_config
    ):
        """find_networking_config returns datasource net config if present."""
        m_cmdline.return_value = {}  # No kernel network config
        m_initramfs.return_value = {}  # no initramfs network config
        self.init.datasource = FakeDataSource(network_config=in_config)
        assert (
            out_config,
            NetworkConfigSource.DS,
        ) == self.init._find_networking_config()

    @mock.patch(M_PATH + "cmdline.read_initramfs_config")
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config")
    def test_wb__find_networking_config_returns_fallback(
        self, m_cmdline, m_initramfs, caplog
    ):
        """find_networking_config returns fallback config if not defined."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        m_initramfs.return_value = {}  # no initramfs network config
        # Neither datasource nor system_info disable or provide network

        fake_cfg = {
            "config": [{"type": "physical", "name": "eth9"}],
            "version": 1,
        }

        def fake_generate_fallback():
            return fake_cfg

        # Monkey patch distro which gets cached on self.init
        distro = self.init.distro
        distro.generate_fallback_config = fake_generate_fallback
        assert (
            fake_cfg,
            NetworkConfigSource.FALLBACK,
        ) == self.init._find_networking_config()
        assert "network config disabled" not in caplog.text

    @mock.patch(M_PATH + "cmdline.read_initramfs_config", return_value={})
    @mock.patch(M_PATH + "cmdline.read_kernel_cmdline_config", return_value={})
    def test_warn_on_empty_network(self, m_cmdline, m_initramfs, caplog):
        """funky whitespace can lead to a network key that is None, which then
        causes fallback. Test warning log on empty network key.
        """
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        m_initramfs.return_value = {}  # no initramfs network config
        # Neither datasource nor system_info disable or provide network
        self.init._cfg = {
            "system_info": {"paths": {"cloud_dir": self.tmpdir}},
            "network": None,
        }
        self.init.datasource = FakeDataSource(network_config={"network": None})

        self.init.distro.generate_fallback_config = dict

        self.init._find_networking_config()
        assert "Empty network config found" in caplog.text

    def test_apply_network_config_disabled(self, caplog):
        """Log when network is disabled by upgraded-network."""
        disable_file = os.path.join(
            self.init.paths.get_cpath("data"), "upgraded-network"
        )

        def fake_network_config():
            return (None, disable_file)

        self.init._find_networking_config = fake_network_config

        self.init.apply_network_config(True)
        assert caplog.records[0].levelname == "INFO"
        assert f"network config is disabled by {disable_file}" in caplog.text

    @pytest.mark.parametrize("instance_dir_present", (True, False))
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.distros.ubuntu.Distro")
    def test_apply_network_on_new_instance(
        self, m_ubuntu, m_macs, instance_dir_present
    ):
        """Call distro apply_network_config methods on is_new_instance."""
        net_cfg = {
            "version": 1,
            "config": [
                {
                    "subnets": [{"type": "dhcp"}],
                    "type": "physical",
                    "name": "eth9",
                    "mac_address": "42:42:42:42:42:42",
                }
            ],
        }

        def fake_network_config():
            return net_cfg, NetworkConfigSource.FALLBACK

        m_macs.return_value = {"42:42:42:42:42:42": "eth9"}

        self.init._find_networking_config = fake_network_config
        if not instance_dir_present:
            self.tmpdir.join("instance").remove()
            self.tmpdir.join("instance-uuid").remove()
        self.init.apply_network_config(True)
        networking = self.init.distro.networking
        networking.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_called_with(
            net_cfg, bring_up=True
        )
        if instance_dir_present:
            assert net_cfg == json.loads(
                self.tmpdir.join("network-config.json").read()
            )
            assert os.path.islink(self.tmpdir.join("network-config.json"))
        else:
            for path in (
                "instance/network-config.json",
                "network-config.json",
            ):
                assert not self.tmpdir.join(path).exists()

    @mock.patch("cloudinit.distros.ubuntu.Distro")
    @mock.patch.dict(
        sources.DataSource.default_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_apply_network_on_same_instance_id(self, m_ubuntu, caplog):
        """Only call distro.networking.apply_network_config_names on same
        instance id."""
        self.init.is_new_instance = self._real_is_new_instance
        old_instance_id = os.path.join(
            self.init.paths.get_cpath("data"), "instance-id"
        )
        write_file(old_instance_id, TEST_INSTANCE_ID)
        net_cfg = {
            "version": 1,
            "config": [
                {
                    "subnets": [{"type": "dhcp"}],
                    "type": "physical",
                    "name": "eth9",
                    "mac_address": "42:42:42:42:42:42",
                }
            ],
        }

        def fake_network_config():
            return net_cfg, NetworkConfigSource.FALLBACK

        self.init._find_networking_config = fake_network_config

        self.init.apply_network_config(True)
        networking = self.init.distro.networking
        networking.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_not_called()
        assert (
            "No network config applied. Neither a new instance nor datasource "
            "network update allowed" in caplog.text
        )

    def _apply_network_setup(self, m_macs):
        old_instance_id = os.path.join(
            self.init.paths.get_cpath("data"), "instance-id"
        )
        write_file(old_instance_id, TEST_INSTANCE_ID)
        net_cfg = {
            "version": 1,
            "config": [
                {
                    "subnets": [{"type": "dhcp"}],
                    "type": "physical",
                    "name": "eth9",
                    "mac_address": "42:42:42:42:42:42",
                }
            ],
        }

        def fake_network_config():
            return net_cfg, NetworkConfigSource.FALLBACK

        m_macs.return_value = {"42:42:42:42:42:42": "eth9"}

        self.init._find_networking_config = fake_network_config
        self.init.datasource = FakeDataSource(paths=self.init.paths)
        self.init.is_new_instance = mock.Mock(return_value=False)
        return net_cfg

    @mock.patch("cloudinit.util._get_cmdline", return_value="")
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.distros.ubuntu.Distro")
    @mock.patch.dict(
        sources.DataSource.default_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE, EventType.BOOT}},
    )
    def test_apply_network_allowed_when_default_boot(
        self, m_ubuntu, m_macs, m_get_cmdline
    ):
        """Apply network if datasource permits BOOT event."""
        net_cfg = self._apply_network_setup(m_macs)

        self.init.apply_network_config(True)
        networking = self.init.distro.networking
        assert (
            mock.call(net_cfg)
            == networking.apply_network_config_names.call_args_list[-1]
        )
        assert (
            mock.call(net_cfg, bring_up=True)
            == self.init.distro.apply_network_config.call_args_list[-1]
        )

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.distros.ubuntu.Distro")
    @mock.patch.dict(
        sources.DataSource.default_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_apply_network_disabled_when_no_default_boot(
        self, m_ubuntu, m_macs, caplog
    ):
        """Don't apply network if datasource has no BOOT event."""
        self._apply_network_setup(m_macs)
        self.init.apply_network_config(True)
        self.init.distro.apply_network_config.assert_not_called()
        assert (
            "No network config applied. Neither a new instance nor datasource "
            "network update allowed" in caplog.text
        )

    @mock.patch("cloudinit.util._get_cmdline", return_value="")
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.distros.ubuntu.Distro")
    @mock.patch.dict(
        sources.DataSource.default_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_apply_network_allowed_with_userdata_overrides(
        self, m_ubuntu, m_macs, m_get_cmdline
    ):
        """Apply network if userdata overrides default config"""
        net_cfg = self._apply_network_setup(m_macs)
        self.init._cfg = {"updates": {"network": {"when": ["boot"]}}}
        self.init.apply_network_config(True)
        networking = self.init.distro.networking
        networking.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_called_with(
            net_cfg, bring_up=True
        )

    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.distros.ubuntu.Distro")
    @mock.patch.dict(
        sources.DataSource.supported_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_apply_network_disabled_when_unsupported(
        self, m_ubuntu, m_macs, caplog
    ):
        """Don't apply network config if unsupported.

        Shouldn't work even when specified as userdata
        """
        self._apply_network_setup(m_macs)

        self.init._cfg = {"updates": {"network": {"when": ["boot"]}}}
        self.init.apply_network_config(True)
        self.init.distro.apply_network_config.assert_not_called()
        assert (
            "No network config applied. Neither a new instance nor datasource "
            "network update allowed" in caplog.text
        )


class TestInit_ReflectCurInstance:
    """Tests for Init._reflect_cur_instance and
    Init._remove_stale_instance_link.

    Regression coverage for the class of bug where paths.instance_link
    (/var/lib/cloud/instance by default) is found to be a real directory
    instead of the symlink cloud-init always expects it to be (or absent).
    Previously this made the unconditional util.del_file() call in
    _reflect_cur_instance raise an uncaught IsADirectoryError, aborting the
    entire 'init' stage before any cloud-config modules could run. See
    GH-3710/LP:#1883903 (a confirmed prior instance of this exact mechanism,
    via cc_final_message) and GH-4282 (an unresolved recurrence of the same
    symptom in a later cloud-init version).
    """

    @pytest.fixture
    def init(self, paths):
        """A stages.Init wired with a real (tmpdir-backed) Paths object and
        a FakeDataSource, so _get_ipath()/_reflect_cur_instance() can run
        end-to-end against real filesystem state.

        Paths.get_ipath() (which _get_ipath()/_reflect_cur_instance() rely
        on) reads paths.datasource directly, a separate attribute from
        Init.datasource, so both must be set to the same datasource here.

        _cfg is set to a non-empty dict rather than {}: Init.read_cfg()'s
        guard is `if not self._cfg`, so an empty-but-set dict is still
        treated as "not yet read" and would trigger a real (unmocked)
        config load -- including a subp call -- the first time something
        in _reflect_cur_instance()/_write_to_cache() touches self.cfg.
        """
        init = stages.Init()
        init._cfg = {"i_dont_care": "about-this-value"}
        init._paths = paths
        ds = FakeDataSource(paths=paths)
        init.datasource = ds
        paths.datasource = ds
        return init

    # _remove_stale_instance_link is exercised end-to-end through both of
    # its callers below, but it's also tested here in isolation: it's a
    # single-responsibility helper with its own contract (heal a directory,
    # otherwise behave exactly like the plain del_file it replaced), and
    # testing it directly documents that contract independently of either
    # caller's surrounding logic.
    def test_remove_stale_instance_link_heals_real_directory(
        self, init, caplog
    ):
        instance_link = init.paths.instance_link
        os.makedirs(instance_link)

        init._remove_stale_instance_link()

        assert not os.path.exists(instance_link)
        assert (
            "unexpectedly exists as a directory rather than a symlink"
            in caplog.text
        )

    def test_remove_stale_instance_link_removes_symlink_silently(
        self, init, tmpdir, caplog
    ):
        """A valid symlink (even to a nonexistent target, as when a
        previous instance directory was already cleaned up) is removed
        via the original plain del_file path, with no warning logged."""
        instance_link = init.paths.instance_link
        os.symlink(str(tmpdir.join("some-instance-dir")), instance_link)

        init._remove_stale_instance_link()

        assert not os.path.exists(instance_link)
        assert "unexpectedly exists as a directory" not in caplog.text

    def test_remove_stale_instance_link_absent_is_a_noop(self, init, caplog):
        instance_link = init.paths.instance_link
        assert not os.path.exists(instance_link)

        init._remove_stale_instance_link()

        assert not os.path.exists(instance_link)
        assert "unexpectedly exists as a directory" not in caplog.text

    def test_remove_stale_instance_link_does_not_follow_nested_symlinks(
        self, init, tmpdir
    ):
        """Safety property: healing a real directory at instance_link
        must never delete anything a symlink *inside* it points to --
        only the symlink entry itself. shutil.rmtree() already guarantees
        this (verified independently against the stdlib), but this test
        pins the guarantee against this specific code path so a future
        change to how the directory is removed can't silently regress it.
        """
        important_elsewhere = tmpdir.mkdir("important_elsewhere")
        important_elsewhere.join("precious.txt").write("precious data")

        instance_link = init.paths.instance_link
        os.makedirs(instance_link)
        os.symlink(
            str(important_elsewhere),
            os.path.join(instance_link, "nested_symlink"),
        )

        init._remove_stale_instance_link()

        assert not os.path.exists(instance_link)
        assert important_elsewhere.exists()
        assert important_elsewhere.join("precious.txt").exists()

    def test_remove_stale_instance_link_refuses_to_rmtree_a_mount_point(
        self, init
    ):
        """Safety property: a mount point at instance_link must never be
        recursively deleted -- rmtree has no filesystem-boundary
        awareness and would delete the mounted filesystem's *contents*
        before failing on the mount point itself, a strictly larger
        blast radius than this function is meant to have. Falls through
        to the plain (non-destructive) del_file() path instead, which
        reproduces the original IsADirectoryError for this one case --
        a real mount point can't be created without root, so this is
        exercised via a targeted mock instead."""
        instance_link = init.paths.instance_link
        os.makedirs(instance_link)

        with mock.patch("os.path.ismount", return_value=True):
            with pytest.raises(IsADirectoryError):
                init._remove_stale_instance_link()

        # Nothing was deleted: del_file's plain os.unlink() failed
        # immediately and left the (simulated) mount point fully intact.
        assert os.path.isdir(instance_link)

    # _get_data_source() has two more call sites for the same instance_link
    # removal, reached well before _reflect_cur_instance()/purge_cache() in
    # a real boot. Exercising it end-to-end would require mocking the whole
    # datasource-discovery machinery (_restore_from_checked_cache,
    # sources.find_source, etc. -- none of which has any existing test
    # coverage in this file to build on), which is disproportionate given
    # _remove_stale_instance_link()'s own behavior is already fully covered
    # above. Instead, these two tests only confirm each call site is wired
    # to the shared, already-tested helper -- not full filesystem behavior.
    def test_get_data_source_removes_stale_instance_link_after_new_source(
        self, init
    ):
        init.datasource = None
        with mock.patch.object(
            init, "_restore_from_checked_cache", return_value=(None, "n/a")
        ), mock.patch.object(
            init, "_remove_stale_instance_link"
        ) as m_remove, mock.patch.object(
            sources, "find_source", return_value=(FakeDataSource(), "Fake")
        ):
            init._get_data_source(existing="trust")

        m_remove.assert_called_once()

    def test_get_data_source_removes_stale_instance_link_on_no_fallback(
        self, init
    ):
        init.datasource = None
        with mock.patch.object(
            init, "_restore_from_checked_cache", return_value=(None, "n/a")
        ), mock.patch.object(
            init, "_remove_stale_instance_link"
        ) as m_remove, mock.patch.object(
            sources,
            "find_source",
            side_effect=sources.DataSourceNotFoundException(),
        ), mock.patch.object(
            init, "_restore_from_cache", return_value=None
        ):
            with pytest.raises(sources.DataSourceNotFoundException):
                init._get_data_source(existing="check")

        m_remove.assert_called_once()

    def test_reflect_cur_instance_normal_case(self, init):
        """Baseline: instance_link absent beforehand (the common case on a
        VM's first boot) ends up as a symlink to the instance directory."""
        instance_link = init.paths.instance_link
        assert not os.path.exists(instance_link)
        # Captured before the call: _reflect_cur_instance() resets cached
        # cfg/paths at the end, so a *second* call to _get_ipath() after it
        # would trigger a real (unmocked) config re-read.
        expected_idir = init._get_ipath()

        init._reflect_cur_instance()

        assert os.path.islink(instance_link)
        assert os.path.realpath(instance_link) == os.path.realpath(
            expected_idir
        )

    def test_reflect_cur_instance_replaces_existing_symlink(
        self, init, tmpdir
    ):
        """A pre-existing (stale, e.g. prior-instance) symlink is replaced
        without error -- this is the expected steady-state behavior."""
        instance_link = init.paths.instance_link
        stale_target = tmpdir.mkdir("stale-target")
        os.symlink(str(stale_target), instance_link)
        expected_idir = init._get_ipath()

        init._reflect_cur_instance()

        assert os.path.islink(instance_link)
        assert os.path.realpath(instance_link) == os.path.realpath(
            expected_idir
        )

    def test_reflect_cur_instance_heals_stale_directory(self, init, caplog):
        """Regression test: if instance_link is a real directory instead of
        a symlink (the promotion bug -- e.g. from some code writing into a
        path under it via ensure_dir_exists=True before the symlink was
        (re)created), _reflect_cur_instance must heal it rather than crash
        with IsADirectoryError."""
        instance_link = init.paths.instance_link
        os.makedirs(instance_link)
        # Simulate a stray write that landed in the wrongly-promoted
        # directory, matching real-world reports of this failure.
        with open(os.path.join(instance_link, "some-stray-file"), "w") as f:
            f.write("stray")
        expected_idir = init._get_ipath()

        init._reflect_cur_instance()

        assert os.path.islink(instance_link)
        assert os.path.realpath(instance_link) == os.path.realpath(
            expected_idir
        )
        assert (
            "unexpectedly exists as a directory rather than a symlink"
            in caplog.text
        )

    def test_purge_cache_heals_stale_directory(self, init):
        """purge_cache(rm_instance_lnk=True) exercises the same
        instance_link removal path (this is the call site that a separate
        real-world report, GH-4282, crashed in) and must be equally
        tolerant of the directory case."""
        instance_link = init.paths.instance_link
        os.makedirs(instance_link)

        count = init.purge_cache(rm_instance_lnk=True)

        assert not os.path.exists(instance_link)
        # 2 == len([boot_finished]) + 1 for instance_link: purge_cache's
        # return value is a count of paths purged, unrelated to this
        # fix's own behavior, but pinned here so a future change to that
        # contract doesn't silently drift unnoticed.
        assert count == 2

    def test_purge_cache_missing_instance_link_is_a_noop(self, init):
        """purge_cache(rm_instance_lnk=True) must not raise when
        instance_link does not exist at all (the common case)."""
        instance_link = init.paths.instance_link
        assert not os.path.exists(instance_link)

        count = init.purge_cache(rm_instance_lnk=True)

        assert not os.path.exists(instance_link)
        # See test_purge_cache_heals_stale_directory for why 2.
        assert count == 2


class TestInit_InitializeFilesystem:
    """Tests for cloudinit.stages.Init._initialize_filesystem.

    TODO: Expand these tests to cover all of _initialize_filesystem's behavior.
    """

    @pytest.fixture
    def init(self, paths):
        """A fixture which yields a stages.Init instance with paths and cfg set

        As it is replaced with a mock, consumers of this fixture can set
        `init._cfg` if the default empty dict configuration is not appropriate.
        """
        with mock.patch(M_PATH + "util.ensure_dirs"):
            init = stages.Init()
            init._cfg = {}
            init._paths = paths
            yield init

    @mock.patch(M_PATH + "util.ensure_file")
    @mock.patch(f"{M_PATH}Init._read_cfg")
    def test_ensure_file_not_called_if_no_log_file_configured(
        self, m_read_cfg, m_ensure_file, init
    ):
        """If no log file is configured, we should not ensure its existence."""
        init._cfg = {}

        init._initialize_filesystem()

        assert 0 == m_ensure_file.call_count

    def test_log_files_existence_is_ensured_if_configured(self, init, tmpdir):
        """If a log file is configured, we should ensure its existence."""
        log_file = tmpdir.join("cloud-init.log")
        init._cfg = {"def_log_file": str(log_file)}

        init._initialize_filesystem()

        assert log_file.exists()
        # Assert we create it 0o640  by default if it doesn't already exist
        assert 0o640 == stat.S_IMODE(log_file.stat().mode)

    @pytest.mark.parametrize(
        "input, expected",
        [
            (0o777, 0o640),
            (0o640, 0o640),
            (0o606, 0o600),
            (0o501, 0o400),
        ],
    )
    def test_existing_file_permissions(self, init, tmpdir, input, expected):
        """Test file permissions are set as expected.

        CIS Hardening requires file mode 0o640 or stricter. Set the
        permissions to the subset of 0o640 and the current
        mode.

        See https://bugs.launchpad.net/cloud-init/+bug/1900837.
        """
        log_file = tmpdir.join("cloud-init.log")
        log_file.ensure()
        log_file.chmod(input)
        init._cfg = {"def_log_file": str(log_file)}
        with mock.patch.object(stages.util, "ensure_file") as ensure:
            init._initialize_filesystem()
            assert expected == ensure.call_args[0][1]


@pytest.mark.parametrize(
    "mode_1, mode_2, expected",
    [
        (0o777, 0o640, 0o640),
        (0o640, 0o777, 0o640),
        (0o640, 0o541, 0o440),
        (0o111, 0o050, 0o010),
        (0o631, 0o640, 0o600),
        (0o661, 0o640, 0o640),
        (0o453, 0o611, 0o411),
    ],
)
def test_strictest_permissions(mode_1, mode_2, expected):
    assert expected == stages.Init._get_strictest_mode(mode_1, mode_2)
