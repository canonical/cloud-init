# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.dhclient_hook."""

from cloudinit import dhclient_hook as dhc
from cloudinit.tests.helpers import CiTestCase, dir2dict, populate_dir

import argparse
import json
import mock
import os


class TestDhclientHook(CiTestCase):

    ex_env = {
        'interface': 'eth0',
        'new_dhcp_lease_time': '3600',
        'new_host_name': 'x1',
        'new_ip_address': '10.145.210.163',
        'new_subnet_mask': '255.255.255.0',
        'old_host_name': 'x1',
        'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
        'pid': '614',
        'reason': 'BOUND',
    }

    # some older versions of dhclient put the same content,
    # but in upper case with DHCP4_ instead of new_
    ex_env_dhcp4 = {
        'REASON': 'BOUND',
        'DHCP4_dhcp_lease_time': '3600',
        'DHCP4_host_name': 'x1',
        'DHCP4_ip_address': '10.145.210.163',
        'DHCP4_subnet_mask': '255.255.255.0',
        'INTERFACE': 'eth0',
        'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
        'pid': '614',
    }

    expected = {
        'dhcp_lease_time': '3600',
        'host_name': 'x1',
        'ip_address': '10.145.210.163',
        'subnet_mask': '255.255.255.0'}

    def setUp(self):
        super(TestDhclientHook, self).setUp()
        self.tmp = self.tmp_dir()

    def test_handle_args(self):
        """quick test of call to handle_args."""
        nic = 'eth0'
        args = argparse.Namespace(event=dhc.UP, interface=nic)
        with mock.patch.dict("os.environ", clear=True, values=self.ex_env):
            dhc.handle_args(dhc.NAME, args, data_d=self.tmp)
        found = dir2dict(self.tmp + os.path.sep)
        self.assertEqual([nic + ".json"], list(found.keys()))
        self.assertEqual(self.expected, json.loads(found[nic + ".json"]))

    def test_run_hook_up_creates_dir(self):
        """If dir does not exist, run_hook should create it."""
        subd = self.tmp_path("subdir", self.tmp)
        nic = 'eth1'
        dhc.run_hook(nic, 'up', data_d=subd, env=self.ex_env)
        self.assertEqual(
            set([nic + ".json"]), set(dir2dict(subd + os.path.sep)))

    def test_run_hook_up(self):
        """Test expected use of run_hook_up."""
        nic = 'eth0'
        dhc.run_hook(nic, 'up', data_d=self.tmp, env=self.ex_env)
        found = dir2dict(self.tmp + os.path.sep)
        self.assertEqual([nic + ".json"], list(found.keys()))
        self.assertEqual(self.expected, json.loads(found[nic + ".json"]))

    def test_run_hook_up_dhcp4_prefix(self):
        """Test run_hook filters correctly with older DHCP4_ data."""
        nic = 'eth0'
        dhc.run_hook(nic, 'up', data_d=self.tmp, env=self.ex_env_dhcp4)
        found = dir2dict(self.tmp + os.path.sep)
        self.assertEqual([nic + ".json"], list(found.keys()))
        self.assertEqual(self.expected, json.loads(found[nic + ".json"]))

    def test_run_hook_down_deletes(self):
        """down should delete the created json file."""
        nic = 'eth1'
        populate_dir(
            self.tmp, {nic + ".json": "{'abcd'}", 'myfile.txt': 'text'})
        dhc.run_hook(nic, 'down', data_d=self.tmp, env={'old_host_name': 'x1'})
        self.assertEqual(
            set(['myfile.txt']),
            set(dir2dict(self.tmp + os.path.sep)))

    def test_get_parser(self):
        """Smoke test creation of get_parser."""
        # cloud-init main uses 'action'.
        event, interface = (dhc.UP, 'mynic0')
        self.assertEqual(
            argparse.Namespace(event=event, interface=interface,
                               action=(dhc.NAME, dhc.handle_args)),
            dhc.get_parser().parse_args([event, interface]))


# vi: ts=4 expandtab
