# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

from cloudinit.config.cc_mounts import create_swapfile


M_PATH = 'cloudinit.config.cc_mounts.'


class TestCreateSwapfile:

    @mock.patch(M_PATH + 'util.subp')
    def test_happy_path(self, m_subp, tmpdir):
        swap_file = tmpdir.join("swap-file")
        fname = str(swap_file)

        # Some of the calls to util.subp should create the swap file; this
        # roughly approximates that
        m_subp.side_effect = lambda *args, **kwargs: swap_file.write('')

        create_swapfile(fname, '')
        assert mock.call(['mkswap', fname]) in m_subp.call_args_list
