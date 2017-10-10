# Copyright (C) 2017 Amazon.com, Inc. or its affiliates
#
# Author: Andrew Jorgensen <ajorgens@amazon.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Tests that SimpleTable works just like PrettyTable for cloud-init.

Not all possible PrettyTable cases are tested because we're not trying to
reimplement the entire library, only the minimal parts we actually use.
"""

from cloudinit.simpletable import SimpleTable
from cloudinit.tests.helpers import CiTestCase

# Examples rendered by cloud-init using PrettyTable
NET_DEVICE_FIELDS = (
    'Device', 'Up', 'Address', 'Mask', 'Scope', 'Hw-Address')
NET_DEVICE_ROWS = (
    ('ens3', True, '172.31.4.203', '255.255.240.0', '.', '0a:1f:07:15:98:70'),
    ('ens3', True, 'fe80::81f:7ff:fe15:9870/64', '.', 'link',
        '0a:1f:07:15:98:70'),
    ('lo', True, '127.0.0.1', '255.0.0.0', '.', '.'),
    ('lo', True, '::1/128', '.', 'host', '.'),
)
NET_DEVICE_TABLE = """\
+--------+------+----------------------------+---------------+-------+-------------------+
| Device |  Up  |          Address           |      Mask     | Scope |     Hw-Address    |
+--------+------+----------------------------+---------------+-------+-------------------+
|  ens3  | True |        172.31.4.203        | 255.255.240.0 |   .   | 0a:1f:07:15:98:70 |
|  ens3  | True | fe80::81f:7ff:fe15:9870/64 |       .       |  link | 0a:1f:07:15:98:70 |
|   lo   | True |         127.0.0.1          |   255.0.0.0   |   .   |         .         |
|   lo   | True |          ::1/128           |       .       |  host |         .         |
+--------+------+----------------------------+---------------+-------+-------------------+"""  # noqa: E501
ROUTE_IPV4_FIELDS = (
    'Route', 'Destination', 'Gateway', 'Genmask', 'Interface', 'Flags')
ROUTE_IPV4_ROWS = (
    ('0', '0.0.0.0', '172.31.0.1', '0.0.0.0', 'ens3', 'UG'),
    ('1', '169.254.0.0', '0.0.0.0', '255.255.0.0', 'ens3', 'U'),
    ('2', '172.31.0.0', '0.0.0.0', '255.255.240.0', 'ens3', 'U'),
)
ROUTE_IPV4_TABLE = """\
+-------+-------------+------------+---------------+-----------+-------+
| Route | Destination |  Gateway   |    Genmask    | Interface | Flags |
+-------+-------------+------------+---------------+-----------+-------+
|   0   |   0.0.0.0   | 172.31.0.1 |    0.0.0.0    |    ens3   |   UG  |
|   1   | 169.254.0.0 |  0.0.0.0   |  255.255.0.0  |    ens3   |   U   |
|   2   |  172.31.0.0 |  0.0.0.0   | 255.255.240.0 |    ens3   |   U   |
+-------+-------------+------------+---------------+-----------+-------+"""

AUTHORIZED_KEYS_FIELDS = (
    'Keytype', 'Fingerprint (md5)', 'Options', 'Comment')
AUTHORIZED_KEYS_ROWS = (
    ('ssh-rsa', '24:c7:41:49:47:12:31:a0:de:6f:62:79:9b:13:06:36', '-',
        'ajorgens'),
)
AUTHORIZED_KEYS_TABLE = """\
+---------+-------------------------------------------------+---------+----------+
| Keytype |                Fingerprint (md5)                | Options | Comment  |
+---------+-------------------------------------------------+---------+----------+
| ssh-rsa | 24:c7:41:49:47:12:31:a0:de:6f:62:79:9b:13:06:36 |    -    | ajorgens |
+---------+-------------------------------------------------+---------+----------+"""  # noqa: E501

# from prettytable import PrettyTable
# pt = PrettyTable(('HEADER',))
# print(pt)
NO_ROWS_FIELDS = ('HEADER',)
NO_ROWS_TABLE = """\
+--------+
| HEADER |
+--------+
+--------+"""


class TestSimpleTable(CiTestCase):

    def test_no_rows(self):
        """An empty table is rendered as PrettyTable would have done it."""
        table = SimpleTable(NO_ROWS_FIELDS)
        self.assertEqual(str(table), NO_ROWS_TABLE)

    def test_net_dev(self):
        """Net device info is rendered as it was with PrettyTable."""
        table = SimpleTable(NET_DEVICE_FIELDS)
        for row in NET_DEVICE_ROWS:
            table.add_row(row)
        self.assertEqual(str(table), NET_DEVICE_TABLE)

    def test_route_ipv4(self):
        """Route IPv4 info is rendered as it was with PrettyTable."""
        table = SimpleTable(ROUTE_IPV4_FIELDS)
        for row in ROUTE_IPV4_ROWS:
            table.add_row(row)
        self.assertEqual(str(table), ROUTE_IPV4_TABLE)

    def test_authorized_keys(self):
        """SSH authorized keys are rendered as they were with PrettyTable."""
        table = SimpleTable(AUTHORIZED_KEYS_FIELDS)
        for row in AUTHORIZED_KEYS_ROWS:
            table.add_row(row)

    def test_get_string(self):
        """get_string() method returns the same content as str()."""
        table = SimpleTable(AUTHORIZED_KEYS_FIELDS)
        for row in AUTHORIZED_KEYS_ROWS:
            table.add_row(row)
        self.assertEqual(table.get_string(), str(table))
