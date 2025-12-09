# This file is part of cloud-init. See LICENSE file for license information.
from cloudinit.distros.parsers import hostname

BASE_HOSTNAME = """
# My super-duper-hostname

blahblah

"""
BASE_HOSTNAME = BASE_HOSTNAME.strip()


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
