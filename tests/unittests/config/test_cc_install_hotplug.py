# This file is part of cloud-init. See LICENSE file for license information.
from collections import namedtuple
from unittest import mock

import pytest

from cloudinit.config.cc_install_hotplug import (
    HOTPLUG_UDEV_PATH,
    HOTPLUG_UDEV_RULES_TEMPLATE,
    handle,
)
from cloudinit.event import EventScope, EventType


@pytest.fixture()
def mocks():
    m_update_enabled = mock.patch("cloudinit.stages.update_event_enabled")
    m_write = mock.patch("cloudinit.util.write_file", autospec=True)
    m_del = mock.patch("cloudinit.util.del_file", autospec=True)
    m_subp = mock.patch("cloudinit.subp.subp")
    m_which = mock.patch("cloudinit.subp.which", return_value=None)
    m_path_exists = mock.patch("os.path.exists", return_value=False)

    yield namedtuple(
        "Mocks", "m_update_enabled m_write m_del m_subp m_which m_path_exists"
    )(
        m_update_enabled.start(),
        m_write.start(),
        m_del.start(),
        m_subp.start(),
        m_which.start(),
        m_path_exists.start(),
    )

    m_update_enabled.stop()
    m_write.stop()
    m_del.stop()
    m_subp.stop()
    m_which.stop()
    m_path_exists.stop()


class TestInstallHotplug:
    @pytest.mark.parametrize("libexec_exists", [True, False])
    def test_rules_installed_when_supported_and_enabled(
        self, mocks, libexec_exists
    ):
        mocks.m_which.return_value = "udevadm"
        mocks.m_update_enabled.return_value = True
        m_cloud = mock.MagicMock()
        m_cloud.datasource.get_supported_events.return_value = {
            EventScope.NETWORK: {EventType.HOTPLUG}
        }

        if libexec_exists:
            libexecdir = "/usr/libexec/cloud-init"
        else:
            libexecdir = "/usr/lib/cloud-init"
        with mock.patch("os.path.exists", return_value=libexec_exists):
            handle(None, {}, m_cloud, mock.Mock(), None)
            mocks.m_write.assert_called_once_with(
                filename=HOTPLUG_UDEV_PATH,
                content=HOTPLUG_UDEV_RULES_TEMPLATE.format(
                    libexecdir=libexecdir
                ),
            )
        assert mocks.m_subp.call_args_list == [
            mock.call(
                [
                    "udevadm",
                    "control",
                    "--reload-rules",
                ]
            )
        ]
        assert mocks.m_del.call_args_list == []

    def test_rules_not_installed_when_unsupported(self, mocks):
        mocks.m_update_enabled.return_value = True
        m_cloud = mock.MagicMock()
        m_cloud.datasource.get_supported_events.return_value = {}

        handle(None, {}, m_cloud, mock.Mock(), None)
        assert mocks.m_write.call_args_list == []
        assert mocks.m_del.call_args_list == []
        assert mocks.m_subp.call_args_list == []

    def test_rules_not_installed_when_disabled(self, mocks):
        mocks.m_update_enabled.return_value = False
        m_cloud = mock.MagicMock()
        m_cloud.datasource.get_supported_events.return_value = {
            EventScope.NETWORK: {EventType.HOTPLUG}
        }

        handle(None, {}, m_cloud, mock.Mock(), None)
        assert mocks.m_write.call_args_list == []
        assert mocks.m_del.call_args_list == []
        assert mocks.m_subp.call_args_list == []

    def test_rules_uninstalled_when_disabled(self, mocks):
        mocks.m_path_exists.return_value = True
        mocks.m_update_enabled.return_value = False
        m_cloud = mock.MagicMock()
        m_cloud.datasource.get_supported_events.return_value = {}

        handle(None, {}, m_cloud, mock.Mock(), None)
        mocks.m_del.assert_called_with(HOTPLUG_UDEV_PATH)
        assert mocks.m_subp.call_args_list == [
            mock.call(
                [
                    "udevadm",
                    "control",
                    "--reload-rules",
                ]
            )
        ]
        assert mocks.m_write.call_args_list == []

    def test_rules_not_installed_when_no_udevadm(self, mocks):
        mocks.m_update_enabled.return_value = True
        m_cloud = mock.MagicMock()
        m_cloud.datasource.get_supported_events.return_value = {
            EventScope.NETWORK: {EventType.HOTPLUG}
        }

        handle(None, {}, m_cloud, mock.Mock(), None)
        assert mocks.m_del.call_args_list == []
        assert mocks.m_write.call_args_list == []
        assert mocks.m_subp.call_args_list == []
