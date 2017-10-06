# Copyright (C) 2014 Vaidas Jablonskis
#
# Author: Vaidas Jablonskis <jablonskis@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import httpretty
import mock
import re

from base64 import b64encode, b64decode
from six.moves.urllib_parse import urlparse

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceGCE

from cloudinit.tests import helpers as test_helpers


GCE_META = {
    'instance/id': '123',
    'instance/zone': 'foo/bar',
    'project/attributes/sshKeys': 'user:ssh-rsa AA2..+aRD0fyVw== root@server',
    'instance/hostname': 'server.project-foo.local',
    # UnicodeDecodeError below if set to ds.userdata instead of userdata_raw
    'instance/attributes/user-data': b'/bin/echo \xff\n',
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
    r'http://metadata.google.internal/computeMetadata/v1/.*')


def _set_mock_metadata(gce_meta=None):
    if gce_meta is None:
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

    # reset is needed. https://github.com/gabrielfalcao/HTTPretty/issues/316
    httpretty.reset()
    httpretty.register_uri(httpretty.GET, MD_URL_RE, body=_request_callback)


@httpretty.activate
class TestDataSourceGCE(test_helpers.HttprettyTestCase):

    def setUp(self):
        self.ds = DataSourceGCE.DataSourceGCE(
            settings.CFG_BUILTIN, None,
            helpers.Paths({}))
        ppatch = self.m_platform_reports_gce = mock.patch(
            'cloudinit.sources.DataSourceGCE.platform_reports_gce')
        self.m_platform_reports_gce = ppatch.start()
        self.m_platform_reports_gce.return_value = True
        self.addCleanup(ppatch.stop)
        super(TestDataSourceGCE, self).setUp()

    def test_connection(self):
        _set_mock_metadata()
        success = self.ds.get_data()
        self.assertTrue(success)

        req_header = httpretty.last_request().headers
        self.assertDictContainsSubset(HEADERS, req_header)

    def test_metadata(self):
        _set_mock_metadata()
        self.ds.get_data()

        shostname = GCE_META.get('instance/hostname').split('.')[0]
        self.assertEqual(shostname,
                         self.ds.get_hostname())

        self.assertEqual(GCE_META.get('instance/id'),
                         self.ds.get_instance_id())

        self.assertEqual(GCE_META.get('instance/attributes/user-data'),
                         self.ds.get_userdata_raw())

    # test partial metadata (missing user-data in particular)
    def test_metadata_partial(self):
        _set_mock_metadata(GCE_META_PARTIAL)
        self.ds.get_data()

        self.assertEqual(GCE_META_PARTIAL.get('instance/id'),
                         self.ds.get_instance_id())

        shostname = GCE_META_PARTIAL.get('instance/hostname').split('.')[0]
        self.assertEqual(shostname, self.ds.get_hostname())

    def test_metadata_encoding(self):
        _set_mock_metadata(GCE_META_ENCODING)
        self.ds.get_data()

        decoded = b64decode(
            GCE_META_ENCODING.get('instance/attributes/user-data'))
        self.assertEqual(decoded, self.ds.get_userdata_raw())

    def test_missing_required_keys_return_false(self):
        for required_key in ['instance/id', 'instance/zone',
                             'instance/hostname']:
            meta = GCE_META_PARTIAL.copy()
            del meta[required_key]
            _set_mock_metadata(meta)
            self.assertEqual(False, self.ds.get_data())
            httpretty.reset()

    def test_project_level_ssh_keys_are_used(self):
        _set_mock_metadata()
        self.ds.get_data()

        # we expect a list of public ssh keys with user names stripped
        self.assertEqual(['ssh-rsa AA2..+aRD0fyVw== root@server'],
                         self.ds.get_public_ssh_keys())

    def test_instance_level_ssh_keys_are_used(self):
        key_content = 'ssh-rsa JustAUser root@server'
        meta = GCE_META.copy()
        meta['instance/attributes/ssh-keys'] = 'user:{0}'.format(key_content)

        _set_mock_metadata(meta)
        self.ds.get_data()

        self.assertIn(key_content, self.ds.get_public_ssh_keys())

    def test_instance_level_keys_replace_project_level_keys(self):
        key_content = 'ssh-rsa JustAUser root@server'
        meta = GCE_META.copy()
        meta['instance/attributes/ssh-keys'] = 'user:{0}'.format(key_content)

        _set_mock_metadata(meta)
        self.ds.get_data()

        self.assertEqual([key_content], self.ds.get_public_ssh_keys())

    def test_only_last_part_of_zone_used_for_availability_zone(self):
        _set_mock_metadata()
        r = self.ds.get_data()
        self.assertEqual(True, r)
        self.assertEqual('bar', self.ds.availability_zone)

    @mock.patch("cloudinit.sources.DataSourceGCE.GoogleMetadataFetcher")
    def test_get_data_returns_false_if_not_on_gce(self, m_fetcher):
        self.m_platform_reports_gce.return_value = False
        ret = self.ds.get_data()
        self.assertEqual(False, ret)
        m_fetcher.assert_not_called()


# vi: ts=4 expandtab
