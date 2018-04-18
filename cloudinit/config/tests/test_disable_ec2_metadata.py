# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_disable_ec2_metadata handler"""

import cloudinit.config.cc_disable_ec2_metadata as ec2_meta

from cloudinit.tests.helpers import CiTestCase, mock

import logging

LOG = logging.getLogger(__name__)

DISABLE_CFG = {'disable_ec2_metadata': 'true'}


class TestEC2MetadataRoute(CiTestCase):

    with_logs = True

    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.which')
    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.subp')
    def test_disable_ifconfig(self, m_subp, m_which):
        """Set the route if ifconfig command is available"""
        m_which.side_effect = lambda x: x if x == 'ifconfig' else None
        ec2_meta.handle('foo', DISABLE_CFG, None, LOG, None)
        m_subp.assert_called_with(
            ['route', 'add', '-host', '169.254.169.254', 'reject'],
            capture=False)

    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.which')
    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.subp')
    def test_disable_ip(self, m_subp, m_which):
        """Set the route if ip command is available"""
        m_which.side_effect = lambda x: x if x == 'ip' else None
        ec2_meta.handle('foo', DISABLE_CFG, None, LOG, None)
        m_subp.assert_called_with(
            ['ip', 'route', 'add', 'prohibit', '169.254.169.254'],
            capture=False)

    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.which')
    @mock.patch('cloudinit.config.cc_disable_ec2_metadata.util.subp')
    def test_disable_no_tool(self, m_subp, m_which):
        """Log error when neither route nor ip commands are available"""
        m_which.return_value = None  # Find neither ifconfig nor ip
        ec2_meta.handle('foo', DISABLE_CFG, None, LOG, None)
        self.assertEqual(
            [mock.call('ip'), mock.call('ifconfig')], m_which.call_args_list)
        m_subp.assert_not_called()

# vi: ts=4 expandtab
