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

import httpretty
import re

from urlparse import urlparse

from cloudinit import settings
from cloudinit import helpers
from cloudinit.sources import DataSourceDigitalOcean

from .. import helpers as test_helpers

# Abbreviated for the test
DO_INDEX = """id
           hostname
           user-data
           vendor-data
           public-keys
           region"""

DO_META = {
    '': DO_INDEX,
    'user-data': '#!/bin/bash\necho "user-data"',
    'vendor-data': '#!/bin/bash\necho "vendor-data"',
    'public-keys': 'ssh-rsa AAAAB3NzaC1yc2EAAAA... neal@digitalocean.com',
    'region': 'nyc3',
    'id': '2000000',
    'hostname': 'cloudinit-test',
}

MD_URL_RE = re.compile(r'http://169.254.169.254/metadata/v1/.*')

def _request_callback(method, uri, headers):
    url_path = urlparse(uri).path
    if url_path.startswith('/metadata/v1/'):
        path = url_path.split('/metadata/v1/')[1:][0]
    else:
        path = None
    if path in DO_META:
        return (200, headers, DO_META.get(path))
    else:
        return (404, headers, '')


class TestDataSourceDigitalOcean(test_helpers.HttprettyTestCase):

    def setUp(self):
        self.ds = DataSourceDigitalOcean.DataSourceDigitalOcean(
            settings.CFG_BUILTIN, None,
            helpers.Paths({}))
        super(TestDataSourceDigitalOcean, self).setUp()

    @httpretty.activate
    def test_connection(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_request_callback)

        success = self.ds.get_data()
        self.assertTrue(success)

    @httpretty.activate
    def test_metadata(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_request_callback)
        self.ds.get_data()

        self.assertEqual(DO_META.get('user-data'),
                         self.ds.get_userdata_raw())

        self.assertEqual(DO_META.get('vendor-data'),
                         self.ds.get_vendordata_raw())

        self.assertEqual([DO_META.get('public-keys')],
                         self.ds.get_public_ssh_keys())

        self.assertEqual(DO_META.get('region'),
                         self.ds.availability_zone)

        self.assertEqual(DO_META.get('id'),
                         self.ds.get_instance_id())

        self.assertEqual(DO_META.get('hostname'),
                         self.ds.get_hostname())

        self.assertEqual('http://mirrors.digitalocean.com/',
                         self.ds.get_package_mirror_info())
