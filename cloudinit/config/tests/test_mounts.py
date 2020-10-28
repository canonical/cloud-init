# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit.config.cc_mounts import create_swapfile
from cloudinit.subp import ProcessExecutionError


M_PATH = 'cloudinit.config.cc_mounts.'


class TestCreateSwapfile:

    @pytest.mark.parametrize('fstype', ('xfs', 'btrfs', 'ext4', 'other'))
    @mock.patch(M_PATH + 'util.get_mount_info')
    @mock.patch(M_PATH + 'subp.subp')
    def test_happy_path(self, m_subp, m_get_mount_info, fstype, tmpdir):
        swap_file = tmpdir.join("swap-file")
        fname = str(swap_file)

        # Some of the calls to subp.subp should create the swap file; this
        # roughly approximates that
        m_subp.side_effect = lambda *args, **kwargs: swap_file.write('')

        m_get_mount_info.return_value = (mock.ANY, fstype)

        create_swapfile(fname, '')
        assert mock.call(['mkswap', fname]) in m_subp.call_args_list

    @mock.patch(M_PATH + "util.get_mount_info")
    @mock.patch(M_PATH + "subp.subp")
    def test_fallback_from_fallocate_to_dd(
        self, m_subp, m_get_mount_info, caplog, tmpdir
    ):
        swap_file = tmpdir.join("swap-file")
        fname = str(swap_file)

        def subp_side_effect(cmd, *args, **kwargs):
            # Mock fallocate failing, to initiate fallback
            if cmd[0] == "fallocate":
                raise ProcessExecutionError()

        m_subp.side_effect = subp_side_effect
        # Use ext4 so both fallocate and dd are valid swap creation methods
        m_get_mount_info.return_value = (mock.ANY, "ext4")

        create_swapfile(fname, "")

        cmds = [args[0][0] for args, _kwargs in m_subp.call_args_list]
        assert "fallocate" in cmds, "fallocate was not called"
        assert "dd" in cmds, "fallocate failure did not fallback to dd"

        assert cmds.index("dd") > cmds.index(
            "fallocate"
        ), "dd ran before fallocate"

        assert mock.call(["mkswap", fname]) in m_subp.call_args_list

        msg = "fallocate swap creation failed, will attempt with dd"
        assert msg in caplog.text
