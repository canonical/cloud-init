# This file is part of cloud-init. See LICENSE file for license information.

"""Tests netinfo module functions and classes."""

from cloudinit.netinfo import netdev_pformat, route_pformat
from cloudinit.tests.helpers import CiTestCase, mock


# Example ifconfig and route output
SAMPLE_IFCONFIG_OUT = """\
enp0s25   Link encap:Ethernet  HWaddr 50:7b:9d:2c:af:91
          inet addr:192.168.2.18  Bcast:192.168.2.255  Mask:255.255.255.0
          inet6 addr: fe80::8107:2b92:867e:f8a6/64 Scope:Link
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1
          RX packets:8106427 errors:55 dropped:0 overruns:0 frame:37
          TX packets:9339739 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:1000
          RX bytes:4953721719 (4.9 GB)  TX bytes:7731890194 (7.7 GB)
          Interrupt:20 Memory:e1200000-e1220000

lo        Link encap:Local Loopback
          inet addr:127.0.0.1  Mask:255.0.0.0
          inet6 addr: ::1/128 Scope:Host
          UP LOOPBACK RUNNING  MTU:65536  Metric:1
          RX packets:579230851 errors:0 dropped:0 overruns:0 frame:0
          TX packets:579230851 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:1
"""

SAMPLE_ROUTE_OUT = '\n'.join([
    '0.0.0.0         192.168.2.1     0.0.0.0         UG        0 0          0'
    ' enp0s25',
    '0.0.0.0         192.168.2.1     0.0.0.0         UG        0 0          0'
    ' wlp3s0',
    '192.168.2.0     0.0.0.0         255.255.255.0   U         0 0          0'
    ' enp0s25'])


NETDEV_FORMATTED_OUT = '\n'.join([
    '+++++++++++++++++++++++++++++++++++++++Net device info+++++++++++++++++++'
    '++++++++++++++++++++',
    '+---------+------+------------------------------+---------------+-------+'
    '-------------------+',
    '|  Device |  Up  |           Address            |      Mask     | Scope |'
    '     Hw-Address    |',
    '+---------+------+------------------------------+---------------+-------+'
    '-------------------+',
    '| enp0s25 | True |         192.168.2.18         | 255.255.255.0 |   .   |'
    ' 50:7b:9d:2c:af:91 |',
    '| enp0s25 | True | fe80::8107:2b92:867e:f8a6/64 |       .       |  link |'
    ' 50:7b:9d:2c:af:91 |',
    '|    lo   | True |          127.0.0.1           |   255.0.0.0   |   .   |'
    '         .         |',
    '|    lo   | True |           ::1/128            |       .       |  host |'
    '         .         |',
    '+---------+------+------------------------------+---------------+-------+'
    '-------------------+'])

ROUTE_FORMATTED_OUT = '\n'.join([
    '+++++++++++++++++++++++++++++Route IPv4 info++++++++++++++++++++++++++'
    '+++',
    '+-------+-------------+-------------+---------------+-----------+-----'
    '--+',
    '| Route | Destination |   Gateway   |    Genmask    | Interface | Flags'
    ' |',
    '+-------+-------------+-------------+---------------+-----------+'
    '-------+',
    '|   0   |   0.0.0.0   | 192.168.2.1 |    0.0.0.0    |   wlp3s0  |'
    '   UG  |',
    '|   1   | 192.168.2.0 |   0.0.0.0   | 255.255.255.0 |  enp0s25  |'
    '   U   |',
    '+-------+-------------+-------------+---------------+-----------+'
    '-------+',
    '++++++++++++++++++++++++++++++++++++++++Route IPv6 info++++++++++'
    '++++++++++++++++++++++++++++++',
    '+-------+-------------+-------------+---------------+---------------+'
    '-----------------+-------+',
    '| Route |    Proto    |    Recv-Q   |     Send-Q    | Local Address |'
    ' Foreign Address | State |',
    '+-------+-------------+-------------+---------------+---------------+'
    '-----------------+-------+',
    '|   0   |   0.0.0.0   | 192.168.2.1 |    0.0.0.0    |       UG      |'
    '        0        |   0   |',
    '|   1   | 192.168.2.0 |   0.0.0.0   | 255.255.255.0 |       U       |'
    '        0        |   0   |',
    '+-------+-------------+-------------+---------------+---------------+'
    '-----------------+-------+'])


class TestNetInfo(CiTestCase):

    maxDiff = None

    @mock.patch('cloudinit.netinfo.util.subp')
    def test_netdev_pformat(self, m_subp):
        """netdev_pformat properly rendering network device information."""
        m_subp.return_value = (SAMPLE_IFCONFIG_OUT, '')
        content = netdev_pformat()
        self.assertEqual(NETDEV_FORMATTED_OUT, content)

    @mock.patch('cloudinit.netinfo.util.subp')
    def test_route_pformat(self, m_subp):
        """netdev_pformat properly rendering network device information."""
        m_subp.return_value = (SAMPLE_ROUTE_OUT, '')
        content = route_pformat()
        self.assertEqual(ROUTE_FORMATTED_OUT, content)
