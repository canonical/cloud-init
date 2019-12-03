# Copyright (C) 2019 Canonical Ltd.
# Copyright (C) 2019 VMware INC.
#
# Author: Xiaofeng Wang <xiaofengw@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from cloudinit.sources.helpers.vmware.imc.guestcust_util import (
    get_tools_config,
)
from cloudinit.tests.helpers import CiTestCase, mock


class TestGuestCustUtil(CiTestCase):
    def test_get_tools_config_not_installed(self):
        """
        This test is designed to verify the behavior if vmware-toolbox-cmd
        is not installed.
        """
        with mock.patch.object(util, 'which', return_value=None):
            self.assertEqual(
                get_tools_config('section', 'key', 'defaultVal'), 'defaultVal')

    def test_get_tools_config_internal_exception(self):
        """
        This test is designed to verify the behavior if internal exception
        is raised.
        """
        with mock.patch.object(util, 'which', return_value='/dummy/path'):
            with mock.patch.object(util, 'subp',
                                   return_value=('key=value', b''),
                                   side_effect=util.ProcessExecutionError(
                                       "subp failed", exit_code=99)):
                # verify return value is 'defaultVal', not 'value'.
                self.assertEqual(
                    get_tools_config('section', 'key', 'defaultVal'),
                    'defaultVal')

    def test_get_tools_config_normal(self):
        """
        This test is designed to verify the value could be parsed from
        key = value of the given [section]
        """
        with mock.patch.object(util, 'which', return_value='/dummy/path'):
            # value is not blank
            with mock.patch.object(util, 'subp',
                                   return_value=('key =   value  ', b'')):
                self.assertEqual(
                    get_tools_config('section', 'key', 'defaultVal'),
                    'value')
            # value is blank
            with mock.patch.object(util, 'subp',
                                   return_value=('key = ', b'')):
                self.assertEqual(
                    get_tools_config('section', 'key', 'defaultVal'),
                    '')
            # value contains =
            with mock.patch.object(util, 'subp',
                                   return_value=('key=Bar=Wark', b'')):
                self.assertEqual(
                    get_tools_config('section', 'key', 'defaultVal'),
                    'Bar=Wark')

            # value contains specific characters
            with mock.patch.object(util, 'subp',
                                   return_value=('[a] b.c_d=e-f', b'')):
                self.assertEqual(
                    get_tools_config('section', 'key', 'defaultVal'),
                    'e-f')

# vi: ts=4 expandtab
