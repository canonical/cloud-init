# This file is part of cloud-init. See LICENSE file for license information.

import re

from cloudinit.distros.parsers.sys_conf import SysConf

from ..helpers import TestCase


# Lots of good examples @
# http://content.hccfl.edu/pollock/AUnix1/SysconfigFilesDesc.txt

class TestSysConfHelper(TestCase):
    # This function was added in 2.7, make it work for 2.6
    def assertRegMatches(self, text, regexp):
        regexp = re.compile(regexp)
        self.assertTrue(regexp.search(text),
                        msg="%s must match %s!" % (text, regexp.pattern))

    def test_parse_no_change(self):
        contents = '''# A comment
USESMBAUTH=no
KEYTABLE=/usr/lib/kbd/keytables/us.map
SHORTDATE=$(date +%y:%m:%d:%H:%M)
HOSTNAME=blahblah
NETMASK0=255.255.255.0
# Inline comment
LIST=$LOGROOT/incremental-list
IPV6TO4_ROUTING='eth0-:0004::1/64 eth1-:0005::1/64'
ETHTOOL_OPTS="-K ${DEVICE} tso on; -G ${DEVICE} rx 256 tx 256"
USEMD5=no'''
        conf = SysConf(contents.splitlines())
        self.assertEqual(conf['HOSTNAME'], 'blahblah')
        self.assertEqual(conf['SHORTDATE'], '$(date +%y:%m:%d:%H:%M)')
        # Should be unquoted
        self.assertEqual(conf['ETHTOOL_OPTS'], ('-K ${DEVICE} tso on; '
                                                '-G ${DEVICE} rx 256 tx 256'))
        self.assertEqual(contents, str(conf))

    def test_parse_shell_vars(self):
        contents = 'USESMBAUTH=$XYZ'
        conf = SysConf(contents.splitlines())
        self.assertEqual(contents, str(conf))
        conf = SysConf('')
        conf['B'] = '${ZZ}d apples'
        # Should be quoted
        self.assertEqual('B="${ZZ}d apples"', str(conf))
        conf = SysConf('')
        conf['B'] = '$? d apples'
        self.assertEqual('B="$? d apples"', str(conf))
        contents = 'IPMI_WATCHDOG_OPTIONS="timeout=60"'
        conf = SysConf(contents.splitlines())
        self.assertEqual('IPMI_WATCHDOG_OPTIONS=timeout=60', str(conf))

    def test_parse_adjust(self):
        contents = 'IPV6TO4_ROUTING="eth0-:0004::1/64 eth1-:0005::1/64"'
        conf = SysConf(contents.splitlines())
        # Should be unquoted
        self.assertEqual('eth0-:0004::1/64 eth1-:0005::1/64',
                         conf['IPV6TO4_ROUTING'])
        conf['IPV6TO4_ROUTING'] = "blah \tblah"
        contents2 = str(conf).strip()
        # Should be requoted due to whitespace
        self.assertRegMatches(contents2,
                              r'IPV6TO4_ROUTING=[\']blah\s+blah[\']')

    def test_parse_no_adjust_shell(self):
        conf = SysConf(''.splitlines())
        conf['B'] = ' $(time)'
        contents = str(conf)
        self.assertEqual('B= $(time)', contents)

    def test_parse_empty(self):
        contents = ''
        conf = SysConf(contents.splitlines())
        self.assertEqual('', str(conf).strip())

    def test_parse_add_new(self):
        contents = 'BLAH=b'
        conf = SysConf(contents.splitlines())
        conf['Z'] = 'd'
        contents = str(conf)
        self.assertIn("Z=d", contents)
        self.assertIn("BLAH=b", contents)

# vi: ts=4 expandtab
