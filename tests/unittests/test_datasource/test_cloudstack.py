# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit import util
from cloudinit.sources.DataSourceCloudStack import (
    DataSourceCloudStack, get_latest_lease)

from cloudinit.tests.helpers import CiTestCase, ExitStack, mock

import os
import time


class TestCloudStackPasswordFetching(CiTestCase):

    def setUp(self):
        super(TestCloudStackPasswordFetching, self).setUp()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        mod_name = 'cloudinit.sources.DataSourceCloudStack'
        self.patches.enter_context(mock.patch('{0}.ec2'.format(mod_name)))
        self.patches.enter_context(mock.patch('{0}.uhelp'.format(mod_name)))
        default_gw = "192.201.20.0"
        get_latest_lease = mock.MagicMock(return_value=None)
        self.patches.enter_context(mock.patch(
            mod_name + '.get_latest_lease', get_latest_lease))

        get_default_gw = mock.MagicMock(return_value=default_gw)
        self.patches.enter_context(mock.patch(
            mod_name + '.get_default_gateway', get_default_gw))

        get_networkd_server_address = mock.MagicMock(return_value=None)
        self.patches.enter_context(mock.patch(
            mod_name + '.dhcp.networkd_get_option_from_leases',
            get_networkd_server_address))
        self.tmp = self.tmp_dir()

    def _set_password_server_response(self, response_string):
        subp = mock.MagicMock(return_value=(response_string, ''))
        self.patches.enter_context(
            mock.patch('cloudinit.sources.DataSourceCloudStack.util.subp',
                       subp))
        return subp

    def test_empty_password_doesnt_create_config(self):
        self._set_password_server_response('')
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    def test_saved_password_doesnt_create_config(self):
        self._set_password_server_response('saved_password')
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    def test_password_sets_password(self):
        password = 'SekritSquirrel'
        self._set_password_server_response(password)
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        ds.get_data()
        self.assertEqual(password, ds.get_config_obj()['password'])

    def test_bad_request_doesnt_stop_ds_from_working(self):
        self._set_password_server_response('bad_request')
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        self.assertTrue(ds.get_data())

    def assertRequestTypesSent(self, subp, expected_request_types):
        request_types = []
        for call in subp.call_args_list:
            args = call[0][0]
            for arg in args:
                if arg.startswith('DomU_Request'):
                    request_types.append(arg.split()[1])
        self.assertEqual(expected_request_types, request_types)

    def test_valid_response_means_password_marked_as_saved(self):
        password = 'SekritSquirrel'
        subp = self._set_password_server_response(password)
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        ds.get_data()
        self.assertRequestTypesSent(subp,
                                    ['send_my_password', 'saved_password'])

    def _check_password_not_saved_for(self, response_string):
        subp = self._set_password_server_response(response_string)
        ds = DataSourceCloudStack(
            {}, None, helpers.Paths({'run_dir': self.tmp}))
        ds.get_data()
        self.assertRequestTypesSent(subp, ['send_my_password'])

    def test_password_not_saved_if_empty(self):
        self._check_password_not_saved_for('')

    def test_password_not_saved_if_already_saved(self):
        self._check_password_not_saved_for('saved_password')

    def test_password_not_saved_if_bad_request(self):
        self._check_password_not_saved_for('bad_request')


class TestGetLatestLease(CiTestCase):

    def _populate_dir_list(self, bdir, files):
        """populate_dir_list([(name, data), (name, data)])

        writes files to bdir, and updates timestamps to ensure
        that their mtime increases with each file."""

        start = int(time.time())
        for num, fname in enumerate(reversed(files)):
            fpath = os.path.sep.join((bdir, fname))
            util.write_file(fpath, fname.encode())
            os.utime(fpath, (start - num, start - num))

    def _pop_and_test(self, files, expected):
        lease_d = self.tmp_dir()
        self._populate_dir_list(lease_d, files)
        self.assertEqual(self.tmp_path(expected, lease_d),
                         get_latest_lease(lease_d))

    def test_skips_dhcpv6_files(self):
        """files started with dhclient6 should be skipped."""
        expected = "dhclient.lease"
        self._pop_and_test([expected, "dhclient6.lease"], expected)

    def test_selects_dhclient_dot_files(self):
        """files named dhclient.lease or dhclient.leases should be used.

        Ubuntu names files dhclient.eth0.leases dhclient6.leases and
        sometimes dhclient.leases."""
        self._pop_and_test(["dhclient.lease"], "dhclient.lease")
        self._pop_and_test(["dhclient.leases"], "dhclient.leases")

    def test_selects_dhclient_dash_files(self):
        """files named dhclient-lease or dhclient-leases should be used.

        Redhat/Centos names files with dhclient--eth0.lease (centos 7) or
        dhclient-eth0.leases (centos 6).
        """
        self._pop_and_test(["dhclient-eth0.lease"], "dhclient-eth0.lease")
        self._pop_and_test(["dhclient--eth0.lease"], "dhclient--eth0.lease")

    def test_ignores_by_extension(self):
        """only .lease or .leases file should be considered."""

        self._pop_and_test(["dhclient.lease", "dhclient.lease.bk",
                            "dhclient.lease-old", "dhclient.leaselease"],
                           "dhclient.lease")

    def test_selects_newest_matching(self):
        """If multiple files match, the newest written should be used."""
        lease_d = self.tmp_dir()
        valid_1 = "dhclient.leases"
        valid_2 = "dhclient.lease"
        valid_1_path = self.tmp_path(valid_1, lease_d)
        valid_2_path = self.tmp_path(valid_2, lease_d)

        self._populate_dir_list(lease_d, [valid_1, valid_2])
        self.assertEqual(valid_2_path, get_latest_lease(lease_d))

        # now update mtime on valid_2 to be older than valid_1 and re-check.
        mtime = int(os.path.getmtime(valid_1_path)) - 1
        os.utime(valid_2_path, (mtime, mtime))

        self.assertEqual(valid_1_path, get_latest_lease(lease_d))


# vi: ts=4 expandtab
