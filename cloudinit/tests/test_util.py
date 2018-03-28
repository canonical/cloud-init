# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.util"""

import logging
from textwrap import dedent

import cloudinit.util as util

from cloudinit.tests.helpers import CiTestCase, mock

LOG = logging.getLogger(__name__)

MOUNT_INFO = [
    '68 0 8:3 / / ro,relatime shared:1 - btrfs /dev/sda1 ro,attr2,inode64',
    '153 68 254:0 / /home rw,relatime shared:101 - xfs /dev/sda2 rw,attr2'
]


class FakeCloud(object):

    def __init__(self, hostname, fqdn):
        self.hostname = hostname
        self.fqdn = fqdn
        self.calls = []

    def get_hostname(self, fqdn=None, metadata_only=None):
        myargs = {}
        if fqdn is not None:
            myargs['fqdn'] = fqdn
        if metadata_only is not None:
            myargs['metadata_only'] = metadata_only
        self.calls.append(myargs)
        if fqdn:
            return self.fqdn
        return self.hostname


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


class TestGetHostnameFqdn(CiTestCase):

    def test_get_hostname_fqdn_from_only_cfg_fqdn(self):
        """When cfg only has the fqdn key, derive hostname and fqdn from it."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'fqdn': 'myhost.domain.com'}, cloud=None)
        self.assertEqual('myhost', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_fqdn_and_hostname(self):
        """When cfg has both fqdn and hostname keys, return them."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'fqdn': 'myhost.domain.com', 'hostname': 'other'}, cloud=None)
        self.assertEqual('other', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_with_domain(self):
        """When cfg has only hostname key which represents a fqdn, use that."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'hostname': 'myhost.domain.com'}, cloud=None)
        self.assertEqual('myhost', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_without_domain(self):
        """When cfg has a hostname without a '.' query cloud.get_hostname."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'hostname': 'myhost'}, cloud=mycloud)
        self.assertEqual('myhost', hostname)
        self.assertEqual('cloudhost.mycloud.com', fqdn)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': False}], mycloud.calls)

    def test_get_hostname_fqdn_from_without_fqdn_or_hostname(self):
        """When cfg has neither hostname nor fqdn cloud.get_hostname."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        hostname, fqdn = util.get_hostname_fqdn(cfg={}, cloud=mycloud)
        self.assertEqual('cloudhost', hostname)
        self.assertEqual('cloudhost.mycloud.com', fqdn)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': False},
             {'metadata_only': False}], mycloud.calls)

    def test_get_hostname_fqdn_from_passes_metadata_only_to_cloud(self):
        """Calls to cloud.get_hostname pass the metadata_only parameter."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={}, cloud=mycloud, metadata_only=True)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': True},
             {'metadata_only': True}], mycloud.calls)


class TestBlkid(CiTestCase):
    ids = {
        "id01": "1111-1111",
        "id02": "22222222-2222",
        "id03": "33333333-3333",
        "id04": "44444444-4444",
        "id05": "55555555-5555-5555-5555-555555555555",
        "id06": "66666666-6666-6666-6666-666666666666",
        "id07": "52894610484658920398",
        "id08": "86753098675309867530",
        "id09": "99999999-9999-9999-9999-999999999999",
    }

    blkid_out = dedent("""\
        /dev/loop0: TYPE="squashfs"
        /dev/loop1: TYPE="squashfs"
        /dev/loop2: TYPE="squashfs"
        /dev/loop3: TYPE="squashfs"
        /dev/sda1: UUID="{id01}" TYPE="vfat" PARTUUID="{id02}"
        /dev/sda2: UUID="{id03}" TYPE="ext4" PARTUUID="{id04}"
        /dev/sda3: UUID="{id05}" TYPE="ext4" PARTUUID="{id06}"
        /dev/sda4: LABEL="default" UUID="{id07}" UUID_SUB="{id08}" """
                       """TYPE="zfs_member" PARTUUID="{id09}"
        /dev/loop4: TYPE="squashfs"
      """)

    maxDiff = None

    def _get_expected(self):
        return ({
            "/dev/loop0": {"DEVNAME": "/dev/loop0", "TYPE": "squashfs"},
            "/dev/loop1": {"DEVNAME": "/dev/loop1", "TYPE": "squashfs"},
            "/dev/loop2": {"DEVNAME": "/dev/loop2", "TYPE": "squashfs"},
            "/dev/loop3": {"DEVNAME": "/dev/loop3", "TYPE": "squashfs"},
            "/dev/loop4": {"DEVNAME": "/dev/loop4", "TYPE": "squashfs"},
            "/dev/sda1": {"DEVNAME": "/dev/sda1", "TYPE": "vfat",
                          "UUID": self.ids["id01"],
                          "PARTUUID": self.ids["id02"]},
            "/dev/sda2": {"DEVNAME": "/dev/sda2", "TYPE": "ext4",
                          "UUID": self.ids["id03"],
                          "PARTUUID": self.ids["id04"]},
            "/dev/sda3": {"DEVNAME": "/dev/sda3", "TYPE": "ext4",
                          "UUID": self.ids["id05"],
                          "PARTUUID": self.ids["id06"]},
            "/dev/sda4": {"DEVNAME": "/dev/sda4", "TYPE": "zfs_member",
                          "LABEL": "default",
                          "UUID": self.ids["id07"],
                          "UUID_SUB": self.ids["id08"],
                          "PARTUUID": self.ids["id09"]},
        })

    @mock.patch("cloudinit.util.subp")
    def test_functional_blkid(self, m_subp):
        m_subp.return_value = (
            self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(), util.blkid())
        m_subp.assert_called_with(["blkid", "-o", "full"], capture=True,
                                  decode="replace")

    @mock.patch("cloudinit.util.subp")
    def test_blkid_no_cache_uses_no_cache(self, m_subp):
        """blkid should turn off cache if disable_cache is true."""
        m_subp.return_value = (
            self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(),
                         util.blkid(disable_cache=True))
        m_subp.assert_called_with(["blkid", "-o", "full", "-c", "/dev/null"],
                                  capture=True, decode="replace")


# vi: ts=4 expandtab
