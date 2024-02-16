from collections import namedtuple
from unittest import mock
from unittest.mock import call

import pytest

from cloudinit import settings
from cloudinit.cmd.devel.hotplug_hook import enable_hotplug, handle_hotplug
from cloudinit.distros import Distro
from cloudinit.event import EventScope, EventType
from cloudinit.net.activators import NetworkActivator
from cloudinit.net.network_state import NetworkState
from cloudinit.sources import DataSource
from cloudinit.stages import Init

M_PATH = "cloudinit.cmd.devel.hotplug_hook."

hotplug_args = namedtuple("hotplug_args", "udevaction, subsystem, devpath")
FAKE_MAC = "11:22:33:44:55:66"


@pytest.fixture
def mocks():
    m_init = mock.MagicMock(spec=Init)
    m_activator = mock.MagicMock(spec=NetworkActivator)
    m_distro = mock.MagicMock(spec=Distro)
    m_distro.network_activator = mock.PropertyMock(return_value=m_activator)
    m_datasource = mock.MagicMock(spec=DataSource)
    m_datasource.distro = m_distro
    m_datasource.skip_hotplug_detect = False
    m_init.datasource = m_datasource
    m_init.fetch.return_value = m_datasource

    read_sys_net = mock.patch(
        "cloudinit.cmd.devel.hotplug_hook.read_sys_net_safe",
        return_value=FAKE_MAC,
    )

    update_event_enabled = mock.patch(
        "cloudinit.stages.update_event_enabled",
        return_value=True,
    )

    m_network_state = mock.MagicMock(spec=NetworkState)
    parse_net = mock.patch(
        "cloudinit.cmd.devel.hotplug_hook.parse_net_config_data",
        return_value=m_network_state,
    )

    sleep = mock.patch("time.sleep")

    read_sys_net.start()
    update_event_enabled.start()
    parse_net.start()
    m_sleep = sleep.start()

    yield namedtuple("mocks", "m_init m_network_state m_activator m_sleep")(
        m_init=m_init,
        m_network_state=m_network_state,
        m_activator=m_activator,
        m_sleep=m_sleep,
    )

    read_sys_net.stop()
    update_event_enabled.stop()
    parse_net.stop()
    sleep.stop()


class TestUnsupportedActions:
    def test_unsupported_subsystem(self, mocks):
        with pytest.raises(
            Exception, match="cannot handle events for subsystem: not_real"
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                subsystem="not_real",
                udevaction="add",
            )

    def test_unsupported_udevaction(self, mocks):
        with pytest.raises(ValueError, match="Unknown action: not_real"):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                subsystem="net",
                udevaction="not_real",
            )


class TestHotplug:
    def test_succcessful_add(self, mocks):
        init = mocks.m_init
        mocks.m_network_state.iter_interfaces.return_value = [
            {
                "mac_address": FAKE_MAC,
            }
        ]
        handle_hotplug(
            hotplug_init=init,
            devpath="/dev/fake",
            udevaction="add",
            subsystem="net",
        )
        init.datasource.update_metadata_if_supported.assert_called_once_with(
            [EventType.HOTPLUG]
        )
        mocks.m_activator.bring_up_interface.assert_called_once_with("fake")
        mocks.m_activator.bring_down_interface.assert_not_called()
        init._write_to_cache.assert_called_once_with()

    def test_successful_remove(self, mocks):
        init = mocks.m_init
        mocks.m_network_state.iter_interfaces.return_value = [{}]
        handle_hotplug(
            hotplug_init=init,
            devpath="/dev/fake",
            udevaction="remove",
            subsystem="net",
        )
        init.datasource.update_metadata_if_supported.assert_called_once_with(
            [EventType.HOTPLUG]
        )
        mocks.m_activator.bring_down_interface.assert_called_once_with("fake")
        mocks.m_activator.bring_up_interface.assert_not_called()
        init._write_to_cache.assert_called_once_with()

    @mock.patch(
        "cloudinit.cmd.devel.hotplug_hook.NetHandler.detect_hotplugged_device"
    )
    @pytest.mark.parametrize("skip", [True, False])
    def test_skip_detected(self, m_detect, skip, mocks):
        mocks.m_init.datasource.skip_hotplug_detect = skip
        expected_call_count = 0 if skip else 1
        handle_hotplug(
            hotplug_init=mocks.m_init,
            devpath="/dev/fake",
            udevaction="add",
            subsystem="net",
        )
        assert m_detect.call_count == expected_call_count

    def test_update_event_disabled(self, mocks, caplog):
        init = mocks.m_init
        with mock.patch(
            "cloudinit.stages.update_event_enabled", return_value=False
        ):
            handle_hotplug(
                hotplug_init=init,
                devpath="/dev/fake",
                udevaction="remove",
                subsystem="net",
            )
        assert "hotplug not enabled for event of type" in caplog.text
        init.datasource.update_metadata_if_supported.assert_not_called()
        mocks.m_activator.bring_up_interface.assert_not_called()
        mocks.m_activator.bring_down_interface.assert_not_called()
        init._write_to_cache.assert_not_called()

    def test_update_metadata_failed(self, mocks):
        mocks.m_init.datasource.update_metadata_if_supported.return_value = (
            False
        )
        with pytest.raises(
            RuntimeError, match="Datasource .* not updated for event hotplug"
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="remove",
                subsystem="net",
            )

    def test_detect_hotplugged_device_not_detected_on_add(self, mocks):
        mocks.m_network_state.iter_interfaces.return_value = [{}]
        with pytest.raises(
            RuntimeError,
            match="Failed to detect {} in updated metadata".format(FAKE_MAC),
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="add",
                subsystem="net",
            )

    def test_detect_hotplugged_device_detected_on_remove(self, mocks):
        mocks.m_network_state.iter_interfaces.return_value = [
            {
                "mac_address": FAKE_MAC,
            }
        ]
        with pytest.raises(
            RuntimeError, match="Failed to detect .* in updated metadata"
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="remove",
                subsystem="net",
            )

    def test_apply_failed_on_add(self, mocks):
        mocks.m_network_state.iter_interfaces.return_value = [
            {
                "mac_address": FAKE_MAC,
            }
        ]
        mocks.m_activator.bring_up_interface.return_value = False
        with pytest.raises(
            RuntimeError, match="Failed to bring up device: /dev/fake"
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="add",
                subsystem="net",
            )

    def test_apply_failed_on_remove(self, mocks):
        mocks.m_network_state.iter_interfaces.return_value = [{}]
        mocks.m_activator.bring_down_interface.return_value = False
        with pytest.raises(
            RuntimeError, match="Failed to bring down device: /dev/fake"
        ):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="remove",
                subsystem="net",
            )

    def test_retry(self, mocks):
        with pytest.raises(RuntimeError):
            handle_hotplug(
                hotplug_init=mocks.m_init,
                devpath="/dev/fake",
                udevaction="add",
                subsystem="net",
            )
        assert mocks.m_sleep.call_count == 5
        assert mocks.m_sleep.call_args_list == [
            call(1),
            call(3),
            call(5),
            call(10),
            call(30),
        ]


@pytest.mark.usefixtures("fake_filesystem")
class TestEnableHotplug:
    @mock.patch(M_PATH + "util.write_file")
    @mock.patch(
        M_PATH + "util.read_hotplug_enabled_file",
        return_value={"scopes": []},
    )
    @mock.patch(M_PATH + "install_hotplug")
    def test_enabling(
        self,
        m_install_hotplug,
        m_read_hotplug_enabled_file,
        m_write_file,
        mocks,
    ):
        mocks.m_init.datasource.get_supported_events.return_value = {
            EventScope.NETWORK: {EventType.HOTPLUG}
        }

        enable_hotplug(mocks.m_init, "net")

        assert [
            call([EventType.HOTPLUG])
        ] == mocks.m_init.datasource.get_supported_events.call_args_list
        assert [call()] == m_read_hotplug_enabled_file.call_args_list
        assert [
            call(
                settings.HOTPLUG_ENABLED_FILE,
                '{"scopes": ["network"]}',
                omode="w",
                mode=0o640,
            )
        ] == m_write_file.call_args_list
        assert [
            call(
                mocks.m_init.datasource,
                network_hotplug_enabled=True,
                cfg=mocks.m_init.cfg,
            )
        ] == m_install_hotplug.call_args_list

    @pytest.mark.parametrize(
        ["supported_events"], [({},), ({EventScope.NETWORK: {}},)]
    )
    @mock.patch(M_PATH + "util.write_file")
    @mock.patch(
        M_PATH + "util.read_hotplug_enabled_file",
        return_value={"scopes": []},
    )
    @mock.patch(M_PATH + "install_hotplug")
    def test_hotplug_not_supported_in_ds(
        self,
        m_install_hotplug,
        m_read_hotplug_enabled_file,
        m_write_file,
        supported_events,
        mocks,
    ):
        mocks.m_init.datasource.get_supported_events.return_value = (
            supported_events
        )
        enable_hotplug(mocks.m_init, "net")

        assert [
            call([EventType.HOTPLUG])
        ] == mocks.m_init.datasource.get_supported_events.call_args_list
        assert [] == m_read_hotplug_enabled_file.call_args_list
        assert [] == m_write_file.call_args_list
        assert [] == m_install_hotplug.call_args_list

    @mock.patch(M_PATH + "util.write_file")
    @mock.patch(
        M_PATH + "util.read_hotplug_enabled_file",
        return_value={"scopes": [EventScope.NETWORK.value]},
    )
    @mock.patch(M_PATH + "install_hotplug")
    def test_hotplug_already_enabled_in_file(
        self,
        m_install_hotplug,
        m_read_hotplug_enabled_file,
        m_write_file,
        mocks,
    ):
        mocks.m_init.datasource.get_supported_events.return_value = {
            EventScope.NETWORK: {EventType.HOTPLUG}
        }
        enable_hotplug(mocks.m_init, "net")

        assert [
            call([EventType.HOTPLUG])
        ] == mocks.m_init.datasource.get_supported_events.call_args_list
        assert [call()] == m_read_hotplug_enabled_file.call_args_list
        assert [] == m_write_file.call_args_list
        assert [] == m_install_hotplug.call_args_list
