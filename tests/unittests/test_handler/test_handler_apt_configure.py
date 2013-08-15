from mocker import MockerTestCase

from cloudinit import util

from cloudinit.config import cc_apt_configure

import os
import re


class TestAptProxyConfig(MockerTestCase):
    def setUp(self):
        super(TestAptProxyConfig, self).setUp()
        self.tmp = self.makeDir()
        self.pfile = os.path.join(self.tmp, "proxy.cfg")
        self.cfile = os.path.join(self.tmp, "config.cfg")

    def _search_apt_config(self, contents, ptype, value):
        print(
            r"acquire::%s::proxy\s+[\"']%s[\"'];\n" % (ptype, value),
            contents, "flags=re.IGNORECASE")
        return(re.search(
            r"acquire::%s::proxy\s+[\"']%s[\"'];\n" % (ptype, value),
            contents, flags=re.IGNORECASE))

    def test_apt_proxy_written(self):
        cfg = {'apt_proxy': 'myproxy'}
        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = str(util.read_file_or_url(self.pfile))
        self.assertTrue(self._search_apt_config(contents, "http", "myproxy"))

    def test_apt_http_proxy_written(self):
        cfg = {'apt_http_proxy': 'myproxy'}
        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = str(util.read_file_or_url(self.pfile))
        self.assertTrue(self._search_apt_config(contents, "http", "myproxy"))

    def test_apt_all_proxy_written(self):
        cfg = {'apt_http_proxy': 'myproxy_http_proxy',
               'apt_https_proxy': 'myproxy_https_proxy',
               'apt_ftp_proxy': 'myproxy_ftp_proxy'}

        values = {'http': cfg['apt_http_proxy'],
                  'https': cfg['apt_https_proxy'],
                  'ftp': cfg['apt_ftp_proxy'],
                  }

        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = str(util.read_file_or_url(self.pfile))

        for ptype, pval in values.iteritems():
            self.assertTrue(self._search_apt_config(contents, ptype, pval))

    def test_proxy_deleted(self):
        util.write_file(self.cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, self.pfile, self.cfile)
        self.assertFalse(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

    def test_proxy_replaced(self):
        util.write_file(self.cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({'apt_proxy': "foo"},
                                          self.pfile, self.cfile)
        self.assertTrue(os.path.isfile(self.pfile))
        contents = str(util.read_file_or_url(self.pfile))
        self.assertTrue(self._search_apt_config(contents, "http", "foo"))

    def test_config_written(self):
        payload = 'this is my apt config'
        cfg = {'apt_config': payload}

        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.cfile))
        self.assertFalse(os.path.isfile(self.pfile))

        self.assertEqual(str(util.read_file_or_url(self.cfile)), payload)

    def test_config_replaced(self):
        util.write_file(self.pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({'apt_config': "foo"},
                                          self.pfile, self.cfile)
        self.assertTrue(os.path.isfile(self.cfile))
        self.assertEqual(str(util.read_file_or_url(self.cfile)), "foo")

    def test_config_deleted(self):
        # if no 'apt_config' is provided, delete any previously written file
        util.write_file(self.pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, self.pfile, self.cfile)
        self.assertFalse(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))


# vi: ts=4 expandtab
