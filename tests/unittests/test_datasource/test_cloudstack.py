# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit.sources.DataSourceCloudStack import DataSourceCloudStack

from ..helpers import TestCase, mock, ExitStack


class TestCloudStackPasswordFetching(TestCase):

    def setUp(self):
        super(TestCloudStackPasswordFetching, self).setUp()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        mod_name = 'cloudinit.sources.DataSourceCloudStack'
        self.patches.enter_context(mock.patch('{0}.ec2'.format(mod_name)))
        self.patches.enter_context(mock.patch('{0}.uhelp'.format(mod_name)))

    def _set_password_server_response(self, response_string):
        subp = mock.MagicMock(return_value=(response_string, ''))
        self.patches.enter_context(
            mock.patch('cloudinit.sources.DataSourceCloudStack.util.subp',
                       subp))
        return subp

    def test_empty_password_doesnt_create_config(self):
        self._set_password_server_response('')
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    def test_saved_password_doesnt_create_config(self):
        self._set_password_server_response('saved_password')
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    def test_password_sets_password(self):
        password = 'SekritSquirrel'
        self._set_password_server_response(password)
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
        ds.get_data()
        self.assertEqual(password, ds.get_config_obj()['password'])

    def test_bad_request_doesnt_stop_ds_from_working(self):
        self._set_password_server_response('bad_request')
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
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
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
        ds.get_data()
        self.assertRequestTypesSent(subp,
                                    ['send_my_password', 'saved_password'])

    def _check_password_not_saved_for(self, response_string):
        subp = self._set_password_server_response(response_string)
        ds = DataSourceCloudStack({}, None, helpers.Paths({}))
        ds.get_data()
        self.assertRequestTypesSent(subp, ['send_my_password'])

    def test_password_not_saved_if_empty(self):
        self._check_password_not_saved_for('')

    def test_password_not_saved_if_already_saved(self):
        self._check_password_not_saved_for('saved_password')

    def test_password_not_saved_if_bad_request(self):
        self._check_password_not_saved_for('bad_request')

# vi: ts=4 expandtab
