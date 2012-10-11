from mocker import MockerTestCase

from cloudinit.distros.parsers.sys_conf import SysConf


# Lots of good examples @
# http://content.hccfl.edu/pollock/AUnix1/SysconfigFilesDesc.txt

class TestSysConfHelper(MockerTestCase):
    def test_parse_no_change(self):
        contents = '''# A comment
USESMBAUTH=no
KEYTABLE=/usr/lib/kbd/keytables/us.map
SHORTDATE=$(date +%y:%m:%d:%H:%M)
HOSTNAME=blahblah
NETMASK0=255.255.255.0
# Inline comment
LIST=$LOGROOT/incremental-list
IPV6TO4_ROUTING="eth0-:0004::1/64 eth1-:0005::1/64"
ETHTOOL_OPTS="-K ${DEVICE} tso on; -G ${DEVICE} rx 256 tx 256"
USEMD5=no'''
        conf = SysConf(contents.splitlines())
        self.assertEquals(conf['HOSTNAME'], 'blahblah')
        self.assertEquals(conf['SHORTDATE'], '$(date +%y:%m:%d:%H:%M)')
        # Should be unquoted
        self.assertEquals(conf['ETHTOOL_OPTS'], ('-K ${DEVICE} tso on; '
                                                 '-G ${DEVICE} rx 256 tx 256'))
        self.assertEquals(contents, str(conf))

    def test_parse_adjust(self):
        contents = 'IPV6TO4_ROUTING="eth0-:0004::1/64 eth1-:0005::1/64"'
        conf = SysConf(contents.splitlines())
        # Should be unquoted
        self.assertEquals('eth0-:0004::1/64 eth1-:0005::1/64',
                          conf['IPV6TO4_ROUTING'])
        conf['IPV6TO4_ROUTING'] = "blah \tblah"
        contents2 = str(conf).strip()
        # Should be requoted due to whitespace
        self.assertEquals('IPV6TO4_ROUTING="blah \tblah"', contents2)

    def test_parse_no_adjust_shell(self):
        conf = SysConf(''.splitlines())
        conf['B'] = ' $(time)'
        contents = str(conf)
        self.assertEquals('B= $(time)', contents)

    def test_parse_empty(self):
        contents = ''
        conf = SysConf(contents.splitlines())
        self.assertEquals('', str(conf).strip())

    def test_parse_add_new(self):
        contents = 'BLAH=b'
        conf = SysConf(contents.splitlines())
        conf['Z'] = 'd'
        contents = str(conf)
        self.assertIn("Z=d", contents)
        self.assertIn("BLAH=b", contents)
        
