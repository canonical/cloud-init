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

from base64 import b64encode, b64decode
from six.moves.urllib_parse import urlparse

from cloudinit import settings
from cloudinit import helpers
from cloudinit.sources import DataSourceGCE

from .. import helpers as test_helpers

GCE_META = {
    'instance/id': '123',
    'instance/zone': 'foo/bar',
    'project/attributes/sshKeys': 'user:ssh-rsa AA2..+aRD0fyVw== root@server',
    'instance/hostname': 'server.project-foo.local',
    'instance/attributes/user-data': b'/bin/echo foo\n',
}

GCE_META_PARTIAL = {
    'instance/id': '1234',
    'instance/hostname': 'server.project-bar.local',
    'instance/zone': 'bar/baz',
}

GCE_META_ENCODING = {
    'instance/id': '12345',
    'instance/hostname': 'server.project-baz.local',
    'instance/zone': 'baz/bang',
    'instance/attributes/user-data': b64encode(b'/bin/echo baz\n'),
    'instance/attributes/user-data-encoding': 'base64',
}

HEADERS = {'X-Google-Metadata-Request': 'True'}
MD_URL_RE = re.compile(
    r'http://metadata.google.internal./computeMetadata/v1/.*')


def _new_request_callback(gce_meta=None):
    if not gce_meta:
        gce_meta = GCE_META

    def _request_callback(method, uri, headers):
        url_path = urlparse(uri).path
        if url_path.startswith('/computeMetadata/v1/'):
            path = url_path.split('/computeMetadata/v1/')[1:][0]
        else:
            path = None
        if path in gce_meta:
            return (200, headers, gce_meta.get(path))
        else:
            return (404, headers, '')

    return _request_callback


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
            body=_new_request_callback())

        success = self.ds.get_data()
        self.assertTrue(success)

        req_header = httpretty.last_request().headers
        self.assertDictContainsSubset(HEADERS, req_header)

    @httpretty.activate
    def test_metadata(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_new_request_callback())
        self.ds.get_data()

        shostname = GCE_META.get('instance/hostname').split('.')[0]
        self.assertEqual(shostname,
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
            body=_new_request_callback(GCE_META_PARTIAL))
        self.ds.get_data()

        self.assertEqual(GCE_META_PARTIAL.get('instance/id'),
                         self.ds.get_instance_id())

        shostname = GCE_META_PARTIAL.get('instance/hostname').split('.')[0]
        self.assertEqual(shostname, self.ds.get_hostname())

    @httpretty.activate
    def test_metadata_encoding(self):
        httpretty.register_uri(
            httpretty.GET, MD_URL_RE,
            body=_new_request_callback(GCE_META_ENCODING))
        self.ds.get_data()

        decoded = b64decode(
            GCE_META_ENCODING.get('instance/attributes/user-data'))
        self.assertEqual(decoded, self.ds.get_userdata_raw())
