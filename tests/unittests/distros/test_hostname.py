# This file is part of cloud-init. See LICENSE file for license information.
import pytest
from cloudinit.distros.parsers import hostname

BASE_HOSTNAME = """
# My super-duper-hostname

blahblah

"""
BASE_HOSTNAME = BASE_HOSTNAME.strip()
COMMENT_ONLY = """
#SUPER-COOL-HOSTNAME


"""
COMMENT_ONLY = COMMENT_ONLY.strip()
MORE_HOSTNAME = """
#SUPER-COOL-HOSTNAME-MOREMORE
iamhostnameone
iamhostnametwo
wearefriends
inthispythonfile
"""
MORE_HOSTNAME = MORE_HOSTNAME.strip()


class TestHostnameHelper:
    def test_parse_same(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        assert str(hn).strip() == BASE_HOSTNAME
        assert hn.hostname == "blahblah"

    def test_no_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        hn.set_hostname("")
        assert hn.hostname == prev_name

    def test_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        assert prev_name == "blahblah"
        hn.set_hostname("bbbbd")
        assert hn.hostname == "bbbbd"
        expected_out = """
# My super-duper-hostname

bbbbd
"""
        assert str(hn).strip() == expected_out.strip()

    def test_no_hostname_returns_none(self):
        hn = hostname.HostnameConf(COMMENT_ONLY)
        assert hn.hostname is None

    def test_set_hostname_appends_when_missing(self):
        hn = hostname.HostnameConf(COMMENT_ONLY)
        hn.set_hostname("newhost")
        assert hn.hostname == "newhost"
        line = str(hn).splitlines()
        assert line[-1] == "newhost"

    def test_multiple_hostnames_raises_ioerror(self):
        hn = hostname.HostnameConf(MORE_HOSTNAME)
        with pytest.raises(IOError):
            _ = hn.hostname

    def test_set_hostname_strips_whitespace(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        hn.set_hostname("    bbbbd   ")
        assert hn.hostname == "bbbbd"
