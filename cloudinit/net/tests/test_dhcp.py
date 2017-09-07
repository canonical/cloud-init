# This file is part of cloud-init. See LICENSE file for license information.

import mock
import os
from textwrap import dedent

from cloudinit.net.dhcp import (
    InvalidDHCPLeaseFileError, maybe_perform_dhcp_discovery,
    parse_dhcp_lease_file, dhcp_discovery)
from cloudinit.util import ensure_file, write_file
from cloudinit.tests.helpers import CiTestCase


class TestParseDHCPLeasesFile(CiTestCase):

    def test_parse_empty_lease_file_errors(self):
        """parse_dhcp_lease_file errors when file content is empty."""
        empty_file = self.tmp_path('leases')
        ensure_file(empty_file)
        with self.assertRaises(InvalidDHCPLeaseFileError) as context_manager:
            parse_dhcp_lease_file(empty_file)
        error = context_manager.exception
        self.assertIn('Cannot parse empty dhcp lease file', str(error))

    def test_parse_malformed_lease_file_content_errors(self):
        """parse_dhcp_lease_file errors when file content isn't dhcp leases."""
        non_lease_file = self.tmp_path('leases')
        write_file(non_lease_file, 'hi mom.')
        with self.assertRaises(InvalidDHCPLeaseFileError) as context_manager:
            parse_dhcp_lease_file(non_lease_file)
        error = context_manager.exception
        self.assertIn('Cannot parse dhcp lease file', str(error))

    def test_parse_multiple_leases(self):
        """parse_dhcp_lease_file returns a list of all leases within."""
        lease_file = self.tmp_path('leases')
        content = dedent("""
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
              renew 4 2017/07/27 18:02:30;
              expire 5 2017/07/28 07:08:15;
            }
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """)
        expected = [
            {'interface': 'wlp3s0', 'fixed-address': '192.168.2.74',
             'subnet-mask': '255.255.255.0', 'routers': '192.168.2.1',
             'renew': '4 2017/07/27 18:02:30',
             'expire': '5 2017/07/28 07:08:15'},
            {'interface': 'wlp3s0', 'fixed-address': '192.168.2.74',
             'subnet-mask': '255.255.255.0', 'routers': '192.168.2.1'}]
        write_file(lease_file, content)
        self.assertItemsEqual(expected, parse_dhcp_lease_file(lease_file))


class TestDHCPDiscoveryClean(CiTestCase):
    with_logs = True

    @mock.patch('cloudinit.net.dhcp.find_fallback_nic')
    def test_no_fallback_nic_found(self, m_fallback_nic):
        """Log and do nothing when nic is absent and no fallback is found."""
        m_fallback_nic.return_value = None  # No fallback nic found
        self.assertEqual({}, maybe_perform_dhcp_discovery())
        self.assertIn(
            'Skip dhcp_discovery: Unable to find fallback nic.',
            self.logs.getvalue())

    def test_provided_nic_does_not_exist(self):
        """When the provided nic doesn't exist, log a message and no-op."""
        self.assertEqual({}, maybe_perform_dhcp_discovery('idontexist'))
        self.assertIn(
            'Skip dhcp_discovery: nic idontexist not found in get_devicelist.',
            self.logs.getvalue())

    @mock.patch('cloudinit.net.dhcp.util.which')
    @mock.patch('cloudinit.net.dhcp.find_fallback_nic')
    def test_absent_dhclient_command(self, m_fallback, m_which):
        """When dhclient doesn't exist in the OS, log the issue and no-op."""
        m_fallback.return_value = 'eth9'
        m_which.return_value = None  # dhclient isn't found
        self.assertEqual({}, maybe_perform_dhcp_discovery())
        self.assertIn(
            'Skip dhclient configuration: No dhclient command found.',
            self.logs.getvalue())

    @mock.patch('cloudinit.net.dhcp.dhcp_discovery')
    @mock.patch('cloudinit.net.dhcp.util.which')
    @mock.patch('cloudinit.net.dhcp.find_fallback_nic')
    def test_dhclient_run_with_tmpdir(self, m_fallback, m_which, m_dhcp):
        """maybe_perform_dhcp_discovery passes tmpdir to dhcp_discovery."""
        m_fallback.return_value = 'eth9'
        m_which.return_value = '/sbin/dhclient'
        m_dhcp.return_value = {'address': '192.168.2.2'}
        self.assertEqual(
            {'address': '192.168.2.2'}, maybe_perform_dhcp_discovery())
        m_dhcp.assert_called_once()
        call = m_dhcp.call_args_list[0]
        self.assertEqual('/sbin/dhclient', call[0][0])
        self.assertEqual('eth9', call[0][1])
        self.assertIn('/tmp/cloud-init-dhcp-', call[0][2])

    @mock.patch('cloudinit.net.dhcp.util.subp')
    def test_dhcp_discovery_run_in_sandbox(self, m_subp):
        """dhcp_discovery brings up the interface and runs dhclient.

        It also returns the parsed dhcp.leases file generated in the sandbox.
        """
        tmpdir = self.tmp_dir()
        dhclient_script = os.path.join(tmpdir, 'dhclient.orig')
        script_content = '#!/bin/bash\necho fake-dhclient'
        write_file(dhclient_script, script_content, mode=0o755)
        lease_content = dedent("""
            lease {
              interface "eth9";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """)
        lease_file = os.path.join(tmpdir, 'dhcp.leases')
        write_file(lease_file, lease_content)
        self.assertItemsEqual(
            [{'interface': 'eth9', 'fixed-address': '192.168.2.74',
              'subnet-mask': '255.255.255.0', 'routers': '192.168.2.1'}],
            dhcp_discovery(dhclient_script, 'eth9', tmpdir))
        # dhclient script got copied
        with open(os.path.join(tmpdir, 'dhclient')) as stream:
            self.assertEqual(script_content, stream.read())
        # Interface was brought up before dhclient called from sandbox
        m_subp.assert_has_calls([
            mock.call(
                ['ip', 'link', 'set', 'dev', 'eth9', 'up'], capture=True),
            mock.call(
                [os.path.join(tmpdir, 'dhclient'), '-1', '-v', '-lf',
                 lease_file, '-pf', os.path.join(tmpdir, 'dhclient.pid'),
                 'eth9', '-sf', '/bin/true'], capture=True)])
