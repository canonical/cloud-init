#
#    Copyright (C) 2014 Neal Shrader
#
#    Author: Neal Shrader <neal@digitalocean.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceDigitalOcean

from .. import helpers as test_helpers
from ..helpers import HttprettyTestCase

httpretty = test_helpers.import_httpretty()

DO_MULTIPLE_KEYS = ["ssh-rsa AAAAB3NzaC1yc2EAAAA... test1@do.co",
                    "ssh-rsa AAAAB3NzaC1yc2EAAAA... test2@do.co"]
DO_SINGLE_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAA... test@do.co"

DO_META = {
    'user_data': 'user_data_here',
    'vendor_data': 'vendor_data_here',
    'public_keys': DO_SINGLE_KEY,
    'region': 'nyc3',
    'id': '2000000',
    'hostname': 'cloudinit-test',
}

MD_URL = 'http://169.254.169.254/metadata/v1.json'


def _mock_dmi():
    return (True, DO_META.get('id'))


def _request_callback(method, uri, headers):
    return (200, headers, json.dumps(DO_META))


class TestDataSourceDigitalOcean(HttprettyTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        self.ds = DataSourceDigitalOcean.DataSourceDigitalOcean(
            settings.CFG_BUILTIN, None,
            helpers.Paths({}))
        self.ds._get_sysinfo = _mock_dmi
        super(TestDataSourceDigitalOcean, self).setUp()

    @httpretty.activate
    def test_connection(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL,
            body=json.dumps(DO_META))

        success = self.ds.get_data()
        self.assertTrue(success)

    @httpretty.activate
    def test_metadata(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL,
            body=_request_callback)
        self.ds.get_data()

        self.assertEqual(DO_META.get('user_data'),
                         self.ds.get_userdata_raw())

        self.assertEqual(DO_META.get('vendor_data'),
                         self.ds.get_vendordata_raw())

        self.assertEqual(DO_META.get('region'),
                         self.ds.availability_zone)

        self.assertEqual(DO_META.get('id'),
                         self.ds.get_instance_id())

        self.assertEqual(DO_META.get('hostname'),
                         self.ds.get_hostname())

        # Single key
        self.assertEqual([DO_META.get('public_keys')],
                         self.ds.get_public_ssh_keys())

        self.assertIsInstance(self.ds.get_public_ssh_keys(), list)

    @httpretty.activate
    def test_multiple_ssh_keys(self):
        DO_META['public_keys'] = DO_MULTIPLE_KEYS
        httpretty.register_uri(
            httpretty.GET, MD_URL,
            body=_request_callback)
        self.ds.get_data()

        # Multiple keys
        self.assertEqual(DO_META.get('public_keys'),
                         self.ds.get_public_ssh_keys())

        self.assertIsInstance(self.ds.get_public_ssh_keys(), list)
