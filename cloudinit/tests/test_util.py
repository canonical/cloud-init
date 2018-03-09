# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.util"""

import logging

import cloudinit.util as util

from cloudinit.tests.helpers import CiTestCase, mock

LOG = logging.getLogger(__name__)

MOUNT_INFO = [
    '68 0 8:3 / / ro,relatime shared:1 - btrfs /dev/sda1 ro,attr2,inode64',
    '153 68 254:0 / /home rw,relatime shared:101 - xfs /dev/sda2 rw,attr2'
]


class TestUtil(CiTestCase):

    def test_parse_mount_info_no_opts_no_arg(self):
        result = util.parse_mount_info('/home', MOUNT_INFO, LOG)
        self.assertEqual(('/dev/sda2', 'xfs', '/home'), result)

    def test_parse_mount_info_no_opts_arg(self):
        result = util.parse_mount_info('/home', MOUNT_INFO, LOG, False)
        self.assertEqual(('/dev/sda2', 'xfs', '/home'), result)

    def test_parse_mount_info_with_opts(self):
        result = util.parse_mount_info('/', MOUNT_INFO, LOG, True)
        self.assertEqual(
            ('/dev/sda1', 'btrfs', '/', 'ro,relatime'),
            result
        )

    @mock.patch('cloudinit.util.get_mount_info')
    def test_mount_is_rw(self, m_mount_info):
        m_mount_info.return_value = ('/dev/sda1', 'btrfs', '/', 'rw,relatime')
        is_rw = util.mount_is_read_write('/')
        self.assertEqual(is_rw, True)

    @mock.patch('cloudinit.util.get_mount_info')
    def test_mount_is_ro(self, m_mount_info):
        m_mount_info.return_value = ('/dev/sda1', 'btrfs', '/', 'ro,relatime')
        is_rw = util.mount_is_read_write('/')
        self.assertEqual(is_rw, False)


class TestShellify(CiTestCase):

    def test_input_dict_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, 'Input.*was.*dict.*xpected',
            util.shellify, {'mykey': 'myval'})

    def test_input_str_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, 'Input.*was.*str.*xpected', util.shellify, "foobar")

    def test_value_with_int_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, 'shellify.*int', util.shellify, ["foo", 1])

    def test_supports_strings_and_lists(self):
        self.assertEqual(
            '\n'.join(["#!/bin/sh", "echo hi mom", "'echo' 'hi dad'",
                       "'echo' 'hi' 'sis'", ""]),
            util.shellify(["echo hi mom", ["echo", "hi dad"],
                           ('echo', 'hi', 'sis')]))
