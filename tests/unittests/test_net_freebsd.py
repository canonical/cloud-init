from cloudinit import net

from cloudinit.tests.helpers import (CiTestCase, mock, readResource)

SAMPLE_FREEBSD_IFCONFIG_OUT = readResource("netinfo/freebsd-ifconfig-output")


class TestInterfacesByMac(CiTestCase):

    @mock.patch('cloudinit.util.subp')
    @mock.patch('cloudinit.util.is_FreeBSD')
    def test_get_interfaces_by_mac(self, mock_is_FreeBSD, mock_subp):
        mock_is_FreeBSD.return_value = True
        mock_subp.return_value = (SAMPLE_FREEBSD_IFCONFIG_OUT, 0)
        a = net.get_interfaces_by_mac()
        assert a == {'52:54:00:50:b7:0d': 'vtnet0',
                     '80:00:73:63:5c:48': 're0.33',
                     '02:14:39:0e:25:00': 'bridge0',
                     '02:ff:60:8c:f3:72': 'vnet0:11'}
