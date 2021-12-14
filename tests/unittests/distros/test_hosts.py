# This file is part of cloud-init. See LICENSE file for license information.

import unittest

from cloudinit.distros.parsers import hosts


BASE_ETC = '''
# Example
127.0.0.1	localhost
192.168.1.10	foo.mydomain.org  foo
192.168.1.10 	bar.mydomain.org  bar
146.82.138.7	master.debian.org      master
209.237.226.90	www.opensource.org
'''
BASE_ETC = BASE_ETC.strip()


class TestHostsHelper(unittest.TestCase):
    def test_parse(self):
        eh = hosts.HostsConf(BASE_ETC)
        self.assertEqual(eh.get_entry('127.0.0.1'), [['localhost']])
        self.assertEqual(eh.get_entry('192.168.1.10'),
                         [['foo.mydomain.org', 'foo'],
                          ['bar.mydomain.org', 'bar']])
        eh = str(eh)
        self.assertTrue(eh.startswith('# Example'))

    def test_add(self):
        eh = hosts.HostsConf(BASE_ETC)
        eh.add_entry('127.0.0.0', 'blah')
        self.assertEqual(eh.get_entry('127.0.0.0'), [['blah']])
        eh.add_entry('127.0.0.3', 'blah', 'blah2', 'blah3')
        self.assertEqual(eh.get_entry('127.0.0.3'),
                         [['blah', 'blah2', 'blah3']])

    def test_del(self):
        eh = hosts.HostsConf(BASE_ETC)
        eh.add_entry('127.0.0.0', 'blah')
        self.assertEqual(eh.get_entry('127.0.0.0'), [['blah']])

        eh.del_entries('127.0.0.0')
        self.assertEqual(eh.get_entry('127.0.0.0'), [])

# vi: ts=4 expandtab
