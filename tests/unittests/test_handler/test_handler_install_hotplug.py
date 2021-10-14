# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

from cloudinit.config.cc_install_hotplug import (
    handle,
    HOTPLUG_UDEV_PATH,
    HOTPLUG_UDEV_RULES,
)


@mock.patch('cloudinit.stages.update_event_enabled')
@mock.patch('cloudinit.util.write_file', autospec=True)
@mock.patch('cloudinit.util.del_file', autospec=True)
@mock.patch('cloudinit.subp.subp')
class TestInstallHotplug:
    @mock.patch('cloudinit.subp.which', return_value='udevadm')
    def test_rules_installed_when_enabled(
        self, m_which, m_subp, m_del, m_write, m_update_enabled
    ):
        m_update_enabled.return_value = True

        handle(None, None, mock.Mock(), mock.Mock(), None)
        m_write.assert_called_once_with(
            filename=HOTPLUG_UDEV_PATH,
            content=HOTPLUG_UDEV_RULES,
        )
        assert m_subp.call_args_list == [mock.call([
            'udevadm', 'control', '--reload-rules',
        ])]
        assert m_del.call_args_list == []

    @mock.patch('os.path.exists', return_value=False)
    def test_rules_not_installed_when_disabled(
        self, m_exists, m_subp, m_del, m_write, m_update_enabled
    ):
        m_update_enabled.return_value = False

        handle(None, None, mock.Mock(), mock.Mock(), None)
        assert m_write.call_args_list == []
        assert m_del.call_args_list == []
        assert m_subp.call_args_list == []

    @mock.patch('os.path.exists', return_value=True)
    def test_rules_uninstalled_when_disabled(
        self, m_exists, m_subp, m_del, m_write, m_update_enabled
    ):
        m_update_enabled.return_value = False

        handle(None, None, mock.Mock(), mock.Mock(), None)
        m_del.assert_called_with(HOTPLUG_UDEV_PATH)
        assert m_subp.call_args_list == [mock.call([
            'udevadm', 'control', '--reload-rules',
        ])]
        assert m_write.call_args_list == []

    @mock.patch('cloudinit.subp.which', return_value=None)
    def test_rules_not_installed_when_no_udevadm(
        self, m_which, m_subp, m_del, m_write, m_update_enabled
    ):
        m_update_enabled.return_value = True

        handle(None, None, mock.Mock(), mock.Mock(), None)
        assert m_del.call_args_list == []
        assert m_write.call_args_list == []
        assert m_subp.call_args_list == []
