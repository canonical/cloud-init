# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.url_helper import oauth_headers, read_file_or_url
from cloudinit.tests.helpers import CiTestCase, mock, skipIf
from cloudinit import util

import httpretty


try:
    import oauthlib
    assert oauthlib  # avoid pyflakes error F401: import unused
    _missing_oauthlib_dep = False
except ImportError:
    _missing_oauthlib_dep = True


class TestOAuthHeaders(CiTestCase):

    def test_oauth_headers_raises_not_implemented_when_oathlib_missing(self):
        """oauth_headers raises a NotImplemented error when oauth absent."""
        with mock.patch.dict('sys.modules', {'oauthlib': None}):
            with self.assertRaises(NotImplementedError) as context_manager:
                oauth_headers(1, 2, 3, 4, 5)
        self.assertEqual(
            'oauth support is not available',
            str(context_manager.exception))

    @skipIf(_missing_oauthlib_dep, "No python-oauthlib dependency")
    @mock.patch('oauthlib.oauth1.Client')
    def test_oauth_headers_calls_oathlibclient_when_available(self, m_client):
        """oauth_headers calls oaut1.hClient.sign with the provided url."""
        class fakeclient(object):
            def sign(self, url):
                # The first and 3rd item of the client.sign tuple are ignored
                return ('junk', url, 'junk2')

        m_client.return_value = fakeclient()

        return_value = oauth_headers(
            'url', 'consumer_key', 'token_key', 'token_secret',
            'consumer_secret')
        self.assertEqual('url', return_value)


class TestReadFileOrUrl(CiTestCase):
    def test_read_file_or_url_str_from_file(self):
        """Test that str(result.contents) on file is text version of contents.
        It should not be "b'data'", but just "'data'" """
        tmpf = self.tmp_path("myfile1")
        data = b'This is my file content\n'
        util.write_file(tmpf, data, omode="wb")
        result = read_file_or_url("file://%s" % tmpf)
        self.assertEqual(result.contents, data)
        self.assertEqual(str(result), data.decode('utf-8'))

    @httpretty.activate
    def test_read_file_or_url_str_from_url(self):
        """Test that str(result.contents) on url is text version of contents.
        It should not be "b'data'", but just "'data'" """
        url = 'http://hostname/path'
        data = b'This is my url content\n'
        httpretty.register_uri(httpretty.GET, url, data)
        result = read_file_or_url(url)
        self.assertEqual(result.contents, data)
        self.assertEqual(str(result), data.decode('utf-8'))
