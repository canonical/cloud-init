import cloudinit.distros.netbsd

import pytest
import unittest.mock as mock


@pytest.mark.parametrize('with_pkgin', (True, False))
@mock.patch("cloudinit.distros.netbsd.os")
def test_init(m_os, with_pkgin):
    print(with_pkgin)
    m_os.path.exists.return_value = with_pkgin
    cfg = {}

    distro = cloudinit.distros.netbsd.NetBSD("netbsd", cfg, None)
    expectation = ['pkgin', '-y', 'full-upgrade'] if with_pkgin else None
    assert distro.pkg_cmd_upgrade_prefix == expectation
    assert [mock.call('/usr/pkg/bin/pkgin')] == m_os.path.exists.call_args_list
