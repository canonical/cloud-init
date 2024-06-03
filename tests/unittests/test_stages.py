# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

"""Tests related to cloudinit.stages module."""
import json
import os
import stat

import pytest

from cloudinit import sources, stages
from cloudinit.event import EventScope, EventType
from cloudinit.helpers import Paths
from cloudinit.sources import DataSource, NetworkConfigSource
from cloudinit.util import sym_link, write_file
from tests.unittests.helpers import mock
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
