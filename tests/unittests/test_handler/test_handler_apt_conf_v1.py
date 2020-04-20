# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_apt_configure
from cloudinit import util

from cloudinit.tests.helpers import TestCase

import copy
import os
import re
import shutil
import tempfile


class TestAptProxyConfig(TestCase):
    def setUp(self):
        super(TestAptProxyConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.pfile = os.path.join(self.tmp, "proxy.cfg")
        self.cfile = os.path.join(self.tmp, "config.cfg")

    def _search_apt_config(self, contents, ptype, value):
        return re.search(
            r"acquire::%s::proxy\s+[\"']%s[\"'];\n" % (ptype, value),
            contents, flags=re.IGNORECASE)

    def test_apt_proxy_written(self):
        cfg = {'proxy': 'myproxy'}
        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = util.load_file(self.pfile)
        self.assertTrue(self._search_apt_config(contents, "http", "myproxy"))

    def test_apt_http_proxy_written(self):
        cfg = {'http_proxy': 'myproxy'}
        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = util.load_file(self.pfile)
        self.assertTrue(self._search_apt_config(contents, "http", "myproxy"))

    def test_apt_all_proxy_written(self):
        cfg = {'http_proxy': 'myproxy_http_proxy',
               'https_proxy': 'myproxy_https_proxy',
               'ftp_proxy': 'myproxy_ftp_proxy'}

        values = {'http': cfg['http_proxy'],
                  'https': cfg['https_proxy'],
                  'ftp': cfg['ftp_proxy'],
                  }

        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

        contents = util.load_file(self.pfile)

        for ptype, pval in values.items():
            self.assertTrue(self._search_apt_config(contents, ptype, pval))

    def test_proxy_deleted(self):
        util.write_file(self.cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, self.pfile, self.cfile)
        self.assertFalse(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))

    def test_proxy_replaced(self):
        util.write_file(self.cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({'proxy': "foo"},
                                          self.pfile, self.cfile)
        self.assertTrue(os.path.isfile(self.pfile))
        contents = util.load_file(self.pfile)
        self.assertTrue(self._search_apt_config(contents, "http", "foo"))

    def test_config_written(self):
        payload = 'this is my apt config'
        cfg = {'conf': payload}

        cc_apt_configure.apply_apt_config(cfg, self.pfile, self.cfile)

        self.assertTrue(os.path.isfile(self.cfile))
        self.assertFalse(os.path.isfile(self.pfile))

        self.assertEqual(util.load_file(self.cfile), payload)

    def test_config_replaced(self):
        util.write_file(self.pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({'conf': "foo"},
                                          self.pfile, self.cfile)
        self.assertTrue(os.path.isfile(self.cfile))
        self.assertEqual(util.load_file(self.cfile), "foo")

    def test_config_deleted(self):
        # if no 'conf' is provided, delete any previously written file
        util.write_file(self.pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, self.pfile, self.cfile)
        self.assertFalse(os.path.isfile(self.pfile))
        self.assertFalse(os.path.isfile(self.cfile))


class TestConversion(TestCase):
    def test_convert_with_apt_mirror_as_empty_string(self):
        # an empty apt_mirror is the same as no apt_mirror
        empty_m_found = cc_apt_configure.convert_to_v3_apt_format(
            {'apt_mirror': ''})
        default_found = cc_apt_configure.convert_to_v3_apt_format({})
        self.assertEqual(default_found, empty_m_found)

    def test_convert_with_apt_mirror(self):
        mirror = 'http://my.mirror/ubuntu'
        f = cc_apt_configure.convert_to_v3_apt_format({'apt_mirror': mirror})
        self.assertIn(mirror, set(m['uri'] for m in f['apt']['primary']))

    def test_no_old_content(self):
        mirror = 'http://my.mirror/ubuntu'
        mydata = {'apt': {'primary': {'arches': ['default'], 'uri': mirror}}}
        expected = copy.deepcopy(mydata)
        self.assertEqual(expected,
                         cc_apt_configure.convert_to_v3_apt_format(mydata))


# vi: ts=4 expandtab
