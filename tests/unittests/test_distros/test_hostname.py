from mocker import MockerTestCase

from cloudinit.distros.parsers import hostname


BASE_HOSTNAME = '''
# My super-duper-hostname

blahblah

'''
BASE_HOSTNAME = BASE_HOSTNAME.strip()


class TestHostnameHelper(MockerTestCase):
    def test_parse_same(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        self.assertEquals(str(hn).strip(), BASE_HOSTNAME)
        self.assertEquals(hn.hostname, 'blahblah')

    def test_no_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        hn.set_hostname("")
        self.assertEquals(hn.hostname, prev_name)

    def test_adjust_hostname(self):
        hn = hostname.HostnameConf(BASE_HOSTNAME)
        prev_name = hn.hostname
        self.assertEquals(prev_name, 'blahblah')
        hn.set_hostname("bbbbd")
        self.assertEquals(hn.hostname, 'bbbbd')
        expected_out = '''
# My super-duper-hostname

bbbbd
'''
        self.assertEquals(str(hn).strip(), expected_out.strip())
