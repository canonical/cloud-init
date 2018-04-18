# This file is part of cloud-init. See LICENSE file for license information.

"""Tests netinfo module functions and classes."""

from copy import copy

from cloudinit.netinfo import netdev_pformat, route_pformat
from cloudinit.tests.helpers import CiTestCase, mock, readResource


# Example ifconfig and route output
SAMPLE_OLD_IFCONFIG_OUT = readResource("netinfo/old-ifconfig-output")
SAMPLE_NEW_IFCONFIG_OUT = readResource("netinfo/new-ifconfig-output")
SAMPLE_IPADDRSHOW_OUT = readResource("netinfo/sample-ipaddrshow-output")
SAMPLE_ROUTE_OUT_V4 = readResource("netinfo/sample-route-output-v4")
SAMPLE_ROUTE_OUT_V6 = readResource("netinfo/sample-route-output-v6")
SAMPLE_IPROUTE_OUT_V4 = readResource("netinfo/sample-iproute-output-v4")
SAMPLE_IPROUTE_OUT_V6 = readResource("netinfo/sample-iproute-output-v6")
NETDEV_FORMATTED_OUT = readResource("netinfo/netdev-formatted-output")
ROUTE_FORMATTED_OUT = readResource("netinfo/route-formatted-output")


class TestNetInfo(CiTestCase):

    maxDiff = None
    with_logs = True

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_netdev_old_nettools_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering old nettools info."""
        m_subp.return_value = (SAMPLE_OLD_IFCONFIG_OUT, '')
        m_which.side_effect = lambda x: x if x == 'ifconfig' else None
        content = netdev_pformat()
        self.assertEqual(NETDEV_FORMATTED_OUT, content)

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_netdev_new_nettools_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering netdev new nettools info."""
        m_subp.return_value = (SAMPLE_NEW_IFCONFIG_OUT, '')
        m_which.side_effect = lambda x: x if x == 'ifconfig' else None
        content = netdev_pformat()
        self.assertEqual(NETDEV_FORMATTED_OUT, content)

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_netdev_iproute_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering ip route info."""
        m_subp.return_value = (SAMPLE_IPADDRSHOW_OUT, '')
        m_which.side_effect = lambda x: x if x == 'ip' else None
        content = netdev_pformat()
        new_output = copy(NETDEV_FORMATTED_OUT)
        # ip route show describes global scopes on ipv4 addresses
        # whereas ifconfig does not. Add proper global/host scope to output.
        new_output = new_output.replace('|   .    | 50:7b', '| global | 50:7b')
        new_output = new_output.replace(
            '255.0.0.0   |   .    |', '255.0.0.0   |  host  |')
        self.assertEqual(new_output, content)

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_netdev_warn_on_missing_commands(self, m_subp, m_which):
        """netdev_pformat warns when missing both ip and 'netstat'."""
        m_which.return_value = None  # Niether ip nor netstat found
        content = netdev_pformat()
        self.assertEqual('\n', content)
        self.assertEqual(
            "WARNING: Could not print networks: missing 'ip' and 'ifconfig'"
            " commands\n",
            self.logs.getvalue())
        m_subp.assert_not_called()

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_route_nettools_pformat(self, m_subp, m_which):
        """route_pformat properly rendering nettools route info."""

        def subp_netstat_route_selector(*args, **kwargs):
            if args[0] == ['netstat', '--route', '--numeric', '--extend']:
                return (SAMPLE_ROUTE_OUT_V4, '')
            if args[0] == ['netstat', '-A', 'inet6', '--route', '--numeric']:
                return (SAMPLE_ROUTE_OUT_V6, '')
            raise Exception('Unexpected subp call %s' % args[0])

        m_subp.side_effect = subp_netstat_route_selector
        m_which.side_effect = lambda x: x if x == 'netstat' else None
        content = route_pformat()
        self.assertEqual(ROUTE_FORMATTED_OUT, content)

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_route_iproute_pformat(self, m_subp, m_which):
        """route_pformat properly rendering ip route info."""

        def subp_iproute_selector(*args, **kwargs):
            if ['ip', '-o', 'route', 'list'] == args[0]:
                return (SAMPLE_IPROUTE_OUT_V4, '')
            v6cmd = ['ip', '--oneline', '-6', 'route', 'list', 'table', 'all']
            if v6cmd == args[0]:
                return (SAMPLE_IPROUTE_OUT_V6, '')
            raise Exception('Unexpected subp call %s' % args[0])

        m_subp.side_effect = subp_iproute_selector
        m_which.side_effect = lambda x: x if x == 'ip' else None
        content = route_pformat()
        self.assertEqual(ROUTE_FORMATTED_OUT, content)

    @mock.patch('cloudinit.netinfo.util.which')
    @mock.patch('cloudinit.netinfo.util.subp')
    def test_route_warn_on_missing_commands(self, m_subp, m_which):
        """route_pformat warns when missing both ip and 'netstat'."""
        m_which.return_value = None  # Niether ip nor netstat found
        content = route_pformat()
        self.assertEqual('\n', content)
        self.assertEqual(
            "WARNING: Could not print routes: missing 'ip' and 'netstat'"
            " commands\n",
            self.logs.getvalue())
        m_subp.assert_not_called()

# vi: ts=4 expandtab
