import sys
import unittest.mock as mock

import pytest

import cloudinit.distros.netbsd


@pytest.mark.parametrize("with_pkgin", (True, False))
@pytest.mark.skipif(
    sys.version_info < (3, 7, 0), reason="Blowfish not available in 3.6"
)
@mock.patch("cloudinit.distros.netbsd.os")
def test_init(m_os, with_pkgin):
    print(with_pkgin)
    m_os.path.exists.return_value = with_pkgin
    cfg = {}

    # patch ifconfig -a
    with mock.patch(
        "cloudinit.distros.networking.subp.subp", return_value=("", None)
    ):
        distro = cloudinit.distros.netbsd.NetBSD("netbsd", cfg, None)
    expectation = ["pkgin", "-y", "full-upgrade"] if with_pkgin else None
    assert distro.pkg_cmd_upgrade_prefix == expectation
    assert [mock.call("/usr/pkg/bin/pkgin")] == m_os.path.exists.call_args_list
