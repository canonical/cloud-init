# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit.config.cc_mounts import create_swapfile


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
