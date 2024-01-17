import unittest.mock as mock

import pytest

try:
    # Blowfish not available in < 3.7, so this has never worked. Ignore failure
    # to import with AttributeError. We need this module imported prior to
    # patching the object, so we can't gate the version with pytest skipif.
    import cloudinit.distros.netbsd
except AttributeError:
    pass


@pytest.mark.parametrize("with_pkgin", (True, False))
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
