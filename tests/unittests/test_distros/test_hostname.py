# This file is part of cloud-init. See LICENSE file for license information.

import unittest

from cloudinit.distros.parsers import hostname


BASE_HOSTNAME = '''
# My super-duper-hostname

blahblah

'''
BASE_HOSTNAME = BASE_HOSTNAME.strip()


class TestHostnameHelper(unittest.TestCase):
    def test_parse_same(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        self.assertEqual(str(hn).strip(), BASE_HOSTNAME)
        self.assertEqual(hn.hostname, 'blahblah')

    def test_no_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        hn.set_hostname("")
        self.assertEqual(hn.hostname, prev_name)

    def test_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        self.assertEqual(prev_name, 'blahblah')
        hn.set_hostname("bbbbd")
        self.assertEqual(hn.hostname, 'bbbbd')
        expected_out = '''
# My super-duper-hostname

bbbbd
'''
        self.assertEqual(str(hn).strip(), expected_out.strip())

# vi: ts=4 expandtab
