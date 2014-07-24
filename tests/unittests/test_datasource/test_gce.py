#
#    Copyright (C) 2014 Vaidas Jablonskis
#
#    Author: Vaidas Jablonskis <jablonskis@gmail.com>
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
from cloudinit.sources import DataSourceGCE

from .. import helpers as test_helpers

GCE_META = {
    'instance/id': '123',
    'instance/zone': 'foo/bar',
    'project/attributes/sshKeys': 'user:ssh-rsa AA2..+aRD0fyVw== root@server',
    'instance/hostname': 'server.project-name.local',
    'instance/attributes/user-data': '/bin/echo foo\n',
}

GCE_META_PARTIAL = {
    'instance/id': '123',
    'instance/hostname': 'server.project-name.local',
}

HEADERS = {'X-Google-Metadata-Request': 'True'}
MD_URL_RE = re.compile(r'http://metadata.google.internal./computeMetadata/v1/.*')


def _request_callback(method, uri, headers):
    url_path = urlparse(uri).path
    if url_path.startswith('/computeMetadata/v1/'):
        path = url_path.split('/computeMetadata/v1/')[1:][0]
    else:
        path = None
    if path in GCE_META:
        return (200, headers, GCE_META.get(path))
    else:
        return (404, headers, '')


class TestDataSourceGCE(test_helpers.HttprettyTestCase):

    def setUp(self):
        self.ds = DataSourceGCE.DataSourceGCE(
            settings.CFG_BUILTIN, None,
            helpers.Paths({}))
        super(TestDataSourceGCE, self).setUp()

    @httpretty.activate
    def test_connection(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_request_callback)

        success = self.ds.get_data()
        self.assertTrue(success)

        req_header = httpretty.last_request().headers
        self.assertDictContainsSubset(HEADERS, req_header)

    @httpretty.activate
    def test_metadata(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_request_callback)
        self.ds.get_data()

        self.assertEqual(GCE_META.get('instance/hostname'),
                         self.ds.get_hostname())

        self.assertEqual(GCE_META.get('instance/id'),
                         self.ds.get_instance_id())

        self.assertEqual(GCE_META.get('instance/zone'),
                         self.ds.availability_zone)

        self.assertEqual(GCE_META.get('instance/attributes/user-data'),
                         self.ds.get_userdata_raw())

        # we expect a list of public ssh keys with user names stripped
        self.assertEqual(['ssh-rsa AA2..+aRD0fyVw== root@server'],
                         self.ds.get_public_ssh_keys())

    # test partial metadata (missing user-data in particular)
    @httpretty.activate
    def test_metadata_partial(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_request_callback)
        self.ds.get_data()

        self.assertEqual(GCE_META_PARTIAL.get('instance/id'),
                         self.ds.get_instance_id())

        self.assertEqual(GCE_META_PARTIAL.get('instance/hostname'),
                         self.ds.get_hostname())
