# This file is part of cloud-init. See LICENSE file for license information.

""" test_handler_apt_source_v1
Testing various config variations of the apt_source config
This calls all things with v1 format to stress the conversion code on top of
the actually tested code.
"""
import os
import re
import shutil
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock
from mock import call

from cloudinit.config import cc_apt_configure
from cloudinit import gpg
from cloudinit import util

from cloudinit.tests.helpers import TestCase

EXPECTEDKEY = """-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1

mI0ESuZLUgEEAKkqq3idtFP7g9hzOu1a8+v8ImawQN4TrvlygfScMU1TIS1eC7UQ
NUA8Qqgr9iUaGnejb0VciqftLrU9D6WYHSKz+EITefgdyJ6SoQxjoJdsCpJ7o9Jy
8PQnpRttiFm4qHu6BVnKnBNxw/z3ST9YMqW5kbMQpfxbGe+obRox59NpABEBAAG0
HUxhdW5jaHBhZCBQUEEgZm9yIFNjb3R0IE1vc2VyiLYEEwECACAFAkrmS1ICGwMG
CwkIBwMCBBUCCAMEFgIDAQIeAQIXgAAKCRAGILvPA2g/d3aEA/9tVjc10HOZwV29
OatVuTeERjjrIbxflO586GLA8cp0C9RQCwgod/R+cKYdQcHjbqVcP0HqxveLg0RZ
FJpWLmWKamwkABErwQLGlM/Hwhjfade8VvEQutH5/0JgKHmzRsoqfR+LMO6OS+Sm
S0ORP6HXET3+jC8BMG4tBWCTK/XEZw==
=ACB2
-----END PGP PUBLIC KEY BLOCK-----"""

ADD_APT_REPO_MATCH = r"^[\w-]+:\w"


class FakeDistro(object):
    """Fake Distro helper object"""
    def update_package_sources(self):
        """Fake update_package_sources helper method"""
        return


class FakeCloud(object):
    """Fake Cloud helper object"""
    def __init__(self):
        self.distro = FakeDistro()


class TestAptSourceConfig(TestCase):
    """TestAptSourceConfig
    Main Class to test apt_source configs
    """
    release = "fantastic"

    def setUp(self):
        super(TestAptSourceConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.aptlistfile = os.path.join(self.tmp, "single-deb.list")
        self.aptlistfile2 = os.path.join(self.tmp, "single-deb2.list")
        self.aptlistfile3 = os.path.join(self.tmp, "single-deb3.list")
        self.join = os.path.join
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search
        # mock fallback filename into writable tmp dir
        self.fallbackfn = os.path.join(self.tmp, "etc/apt/sources.list.d/",
                                       "cloud_config_sources.list")

        self.fakecloud = FakeCloud()

        rpatcher = mock.patch("cloudinit.util.lsb_release")
        get_rel = rpatcher.start()
        get_rel.return_value = {'codename': self.release}
        self.addCleanup(rpatcher.stop)
        apatcher = mock.patch("cloudinit.util.get_architecture")
        get_arch = apatcher.start()
        get_arch.return_value = 'amd64'
        self.addCleanup(apatcher.stop)

    def _get_default_params(self):
        """get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = self.release
        params['MIRROR'] = "http://archive.ubuntu.com/ubuntu"
        return params

    def wrapv1conf(self, cfg):
        params = self._get_default_params()
        # old v1 list format under old keys, but callabe to main handler
        # disable source.list rendering and set mirror to avoid other code
        return {'apt_preserve_sources_list': True,
                'apt_mirror': params['MIRROR'],
                'apt_sources': cfg}

    def myjoin(self, *args, **kwargs):
        """myjoin - redir into writable tmpdir"""
        if (args[0] == "/etc/apt/sources.list.d/" and
                args[1] == "cloud_config_sources.list" and
                len(args) == 2):
            return self.join(self.tmp, args[0].lstrip("/"), args[1])
        else:
            return self.join(*args, **kwargs)

    def apt_src_basic(self, filename, cfg):
        """apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        cfg = self.wrapv1conf(cfg)

        cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic(self):
        """Test deb source string, overwrite mirror and filename"""
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted'),
               'filename': self.aptlistfile}
        self.apt_src_basic(self.aptlistfile, [cfg])

    def test_apt_src_basic_dict(self):
        """Test deb source string, overwrite mirror and filename (dict)"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://archive.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')}}
        self.apt_src_basic(self.aptlistfile, cfg)

    def apt_src_basic_tri(self, cfg):
        """apt_src_basic_tri
        Test Fix three deb source string, has to overwrite mirror conf in
        params. Test with filenames provided in config.
        generic part to check three files with different content
        """
        self.apt_src_basic(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        contents = util.load_file(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = util.load_file(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic_tri(self):
        """Test Fix three deb source string with filenames"""
        cfg1 = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                           ' karmic-backports'
                           ' main universe multiverse restricted'),
                'filename': self.aptlistfile}
        cfg2 = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                           ' precise-backports'
                           ' main universe multiverse restricted'),
                'filename': self.aptlistfile2}
        cfg3 = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                           ' lucid-backports'
                           ' main universe multiverse restricted'),
                'filename': self.aptlistfile3}
        self.apt_src_basic_tri([cfg1, cfg2, cfg3])

    def test_apt_src_basic_dict_tri(self):
        """Test Fix three deb source string with filenames (dict)"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://archive.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')},
               self.aptlistfile2: {'source':
                                   ('deb http://archive.ubuntu.com/ubuntu'
                                    ' precise-backports'
                                    ' main universe multiverse restricted')},
               self.aptlistfile3: {'source':
                                   ('deb http://archive.ubuntu.com/ubuntu'
                                    ' lucid-backports'
                                    ' main universe multiverse restricted')}}
        self.apt_src_basic_tri(cfg)

    def test_apt_src_basic_nofn(self):
        """Test Fix three deb source string without filenames (dict)"""
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted')}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_basic(self.fallbackfn, [cfg])

    def apt_src_replacement(self, filename, cfg):
        """apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        cfg = self.wrapv1conf(cfg)
        params = self._get_default_params()
        cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace(self):
        """Test Autoreplacement of MIRROR and RELEASE in source specs"""
        cfg = {'source': 'deb $MIRROR $RELEASE multiverse',
               'filename': self.aptlistfile}
        self.apt_src_replacement(self.aptlistfile, [cfg])

    def apt_src_replace_tri(self, cfg):
        """apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self.apt_src_replacement(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        params = self._get_default_params()
        contents = util.load_file(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "main"),
                                  contents, flags=re.IGNORECASE))
        contents = util.load_file(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "universe"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace_tri(self):
        """Test triple Autoreplacement of MIRROR and RELEASE in source specs"""
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        self.apt_src_replace_tri([cfg1, cfg2, cfg3])

    def test_apt_src_replace_dict_tri(self):
        """Test triple Autoreplacement in source specs (dict)"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused': {'source': 'deb $MIRROR $RELEASE main',
                           'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self.apt_src_replace_tri(cfg)

    def test_apt_src_replace_nofn(self):
        """Test Autoreplacement of MIRROR and RELEASE in source specs nofile"""
        cfg = {'source': 'deb $MIRROR $RELEASE multiverse'}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_replacement(self.fallbackfn, [cfg])

    def apt_src_keyid(self, filename, cfg, keynum):
        """apt_src_keyid
        Test specification of a source + keyid
        """
        cfg = self.wrapv1conf(cfg)

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1234', '')) as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        # check if it added the right ammount of keys
        calls = []
        for _ in range(keynum):
            calls.append(call(['apt-key', 'add', '-'],
                              data=b'fakekey 1234',
                              target=None))
        mockobj.assert_has_calls(calls, any_order=True)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyid(self):
        """Test specification of a source + keyid with filename being set"""
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'keyid': "03683F77",
               'filename': self.aptlistfile}
        self.apt_src_keyid(self.aptlistfile, [cfg], 1)

    def test_apt_src_keyid_tri(self):
        """Test 3x specification of a source + keyid with filename being set"""
        cfg1 = {'source': ('deb '
                           'http://ppa.launchpad.net/'
                           'smoser/cloud-init-test/ubuntu'
                           ' xenial main'),
                'keyid': "03683F77",
                'filename': self.aptlistfile}
        cfg2 = {'source': ('deb '
                           'http://ppa.launchpad.net/'
                           'smoser/cloud-init-test/ubuntu'
                           ' xenial universe'),
                'keyid': "03683F77",
                'filename': self.aptlistfile2}
        cfg3 = {'source': ('deb '
                           'http://ppa.launchpad.net/'
                           'smoser/cloud-init-test/ubuntu'
                           ' xenial multiverse'),
                'keyid': "03683F77",
                'filename': self.aptlistfile3}

        self.apt_src_keyid(self.aptlistfile, [cfg1, cfg2, cfg3], 3)
        contents = util.load_file(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "universe"),
                                  contents, flags=re.IGNORECASE))
        contents = util.load_file(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyid_nofn(self):
        """Test specification of a source + keyid without filename being set"""
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'keyid': "03683F77"}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_keyid(self.fallbackfn, [cfg], 1)

    def apt_src_key(self, filename, cfg):
        """apt_src_key
        Test specification of a source + key
        """
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        mockobj.assert_called_with(['apt-key', 'add', '-'],
                                   data=b'fakekey 4321', target=None)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_key(self):
        """Test specification of a source + key with filename being set"""
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321",
               'filename': self.aptlistfile}
        self.apt_src_key(self.aptlistfile, cfg)

    def test_apt_src_key_nofn(self):
        """Test specification of a source + key without filename being set"""
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321"}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_key(self.fallbackfn, cfg)

    def test_apt_src_keyonly(self):
        """Test specifying key without source"""
        cfg = {'key': "fakekey 4242",
               'filename': self.aptlistfile}
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        mockobj.assert_called_once_with(['apt-key', 'add', '-'],
                                        data=b'fakekey 4242', target=None)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyidonly(self):
        """Test specification of a keyid without source"""
        cfg = {'keyid': "03683F77",
               'filename': self.aptlistfile}
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)

        mockobj.assert_called_with(['apt-key', 'add', '-'],
                                   data=b'fakekey 1212', target=None)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def apt_src_keyid_real(self, cfg, expectedkey):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        key = cfg['keyid']
        keyserver = cfg.get('keyserver', 'keyserver.ubuntu.com')
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(cc_apt_configure, 'add_apt_key_raw') as mockkey:
            with mock.patch.object(gpg, 'getkeybyid',
                                   return_value=expectedkey) as mockgetkey:
                cc_apt_configure.handle("test", cfg, self.fakecloud,
                                        None, None)

        mockgetkey.assert_called_with(key, keyserver)
        mockkey.assert_called_with(expectedkey, None)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyid_real(self):
        """test_apt_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {'keyid': keyid,
               'filename': self.aptlistfile}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_longkeyid_real(self):
        """test_apt_src_longkeyid_real - Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {'keyid': keyid,
               'filename': self.aptlistfile}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_longkeyid_ks_real(self):
        """test_apt_src_longkeyid_ks_real - Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {'keyid': keyid,
               'keyserver': 'keys.gnupg.net',
               'filename': self.aptlistfile}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_ppa(self):
        """Test adding a ppa"""
        cfg = {'source': 'ppa:smoser/cloud-init-test',
               'filename': self.aptlistfile}
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud, None, None)
        mockobj.assert_called_once_with(['add-apt-repository',
                                         'ppa:smoser/cloud-init-test'],
                                        target=None)

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_ppa_tri(self):
        """Test adding three ppa's"""
        cfg1 = {'source': 'ppa:smoser/cloud-init-test',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'ppa:smoser/cloud-init-test2',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'ppa:smoser/cloud-init-test3',
                'filename': self.aptlistfile3}
        cfg = self.wrapv1conf([cfg1, cfg2, cfg3])

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.handle("test", cfg, self.fakecloud,
                                    None, None)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test'],
                      target=None),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2'],
                      target=None),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'],
                      target=None)]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))
        self.assertFalse(os.path.isfile(self.aptlistfile2))
        self.assertFalse(os.path.isfile(self.aptlistfile3))

    def test_convert_to_new_format(self):
        """Test the conversion of old to new format"""
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        cfg = {'apt_sources': [cfg1, cfg2, cfg3]}
        checkcfg = {self.aptlistfile: {'filename': self.aptlistfile,
                                       'source': 'deb $MIRROR $RELEASE '
                                                 'multiverse'},
                    self.aptlistfile2: {'filename': self.aptlistfile2,
                                        'source': 'deb $MIRROR $RELEASE main'},
                    self.aptlistfile3: {'filename': self.aptlistfile3,
                                        'source': 'deb $MIRROR $RELEASE '
                                                  'universe'}}

        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg)
        self.assertEqual(newcfg['apt']['sources'], checkcfg)

        # convert again, should stay the same
        newcfg2 = cc_apt_configure.convert_to_v3_apt_format(newcfg)
        self.assertEqual(newcfg2['apt']['sources'], checkcfg)

        # should work without raising an exception
        cc_apt_configure.convert_to_v3_apt_format({})

        with self.assertRaises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format({'apt_sources': 5})

    def test_convert_to_new_format_collision(self):
        """Test the conversion of old to new format with collisions
           That matches e.g. the MAAS case specifying old and new config"""
        cfg_1_and_3 = {'apt': {'proxy': 'http://192.168.122.1:8000/'},
                       'apt_proxy': 'http://192.168.122.1:8000/'}
        cfg_3_only = {'apt': {'proxy': 'http://192.168.122.1:8000/'}}
        cfgconflict = {'apt': {'proxy': 'http://192.168.122.1:8000/'},
                       'apt_proxy': 'ftp://192.168.122.1:8000/'}

        # collision (equal)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3)
        self.assertEqual(newcfg, cfg_3_only)
        # collision (equal, so ok to remove)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_3_only)
        self.assertEqual(newcfg, cfg_3_only)
        # collision (unequal)
        match = "Old and New.*unequal.*apt_proxy"
        with self.assertRaisesRegex(ValueError, match):
            cc_apt_configure.convert_to_v3_apt_format(cfgconflict)

    def test_convert_to_new_format_dict_collision(self):
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        fullv3 = {self.aptlistfile: {'filename': self.aptlistfile,
                                     'source': 'deb $MIRROR $RELEASE '
                                               'multiverse'},
                  self.aptlistfile2: {'filename': self.aptlistfile2,
                                      'source': 'deb $MIRROR $RELEASE main'},
                  self.aptlistfile3: {'filename': self.aptlistfile3,
                                      'source': 'deb $MIRROR $RELEASE '
                                                'universe'}}
        cfg_3_only = {'apt': {'sources': fullv3}}
        cfg_1_and_3 = {'apt_sources': [cfg1, cfg2, cfg3]}
        cfg_1_and_3.update(cfg_3_only)

        # collision (equal, so ok to remove)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3)
        self.assertEqual(newcfg, cfg_3_only)
        # no old spec (same result)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_3_only)
        self.assertEqual(newcfg, cfg_3_only)

        diff = {self.aptlistfile: {'filename': self.aptlistfile,
                                   'source': 'deb $MIRROR $RELEASE '
                                             'DIFFERENTVERSE'},
                self.aptlistfile2: {'filename': self.aptlistfile2,
                                    'source': 'deb $MIRROR $RELEASE main'},
                self.aptlistfile3: {'filename': self.aptlistfile3,
                                    'source': 'deb $MIRROR $RELEASE '
                                              'universe'}}
        cfg_3_only = {'apt': {'sources': diff}}
        cfg_1_and_3_different = {'apt_sources': [cfg1, cfg2, cfg3]}
        cfg_1_and_3_different.update(cfg_3_only)

        # collision (unequal by dict having a different entry)
        with self.assertRaises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3_different)

        missing = {self.aptlistfile: {'filename': self.aptlistfile,
                                      'source': 'deb $MIRROR $RELEASE '
                                                'multiverse'}}
        cfg_3_only = {'apt': {'sources': missing}}
        cfg_1_and_3_missing = {'apt_sources': [cfg1, cfg2, cfg3]}
        cfg_1_and_3_missing.update(cfg_3_only)
        # collision (unequal by dict missing an entry)
        with self.assertRaises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3_missing)


# vi: ts=4 expandtab
