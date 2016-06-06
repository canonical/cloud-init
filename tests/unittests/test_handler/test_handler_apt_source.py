""" test_handler_apt_source
Testing various config variations of the apt_source config
"""
import os
import re
import shutil
import socket
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock
from mock import call

from cloudinit.config import cc_apt_configure
from cloudinit import util

from ..helpers import TestCase
from .. import helpers as t_help

BIN_APT = "/usr/bin/apt"

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


def load_tfile_or_url(*args, **kwargs):
    """load_tfile_or_url
    load file and return content after decoding
    """
    return util.decode_binary(util.read_file_or_url(*args, **kwargs).contents)


# This feature is apt specific and thereby is disabled in environments without
@t_help.skipIf(not os.path.isfile(BIN_APT), "no apt")
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
        # mock fallback filename into writable tmp dir
        self.fallbackfn = os.path.join(self.tmp, "etc/apt/sources.list.d/",
                                       "cloud_config_sources.list")
        self.orig_gpg_recv_key = util.gpg_recv_key

        patcher = mock.patch("cloudinit.config.cc_apt_configure.get_release")
        get_rel = patcher.start()
        get_rel.return_value = self.release
        self.addCleanup(patcher.stop)

    @staticmethod
    def _get_default_params():
        """get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = cc_apt_configure.get_release()
        params['MIRROR'] = "http://archive.ubuntu.com/ubuntu"
        return params

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
        params = self._get_default_params()

        cc_apt_configure.add_apt_sources(cfg, params)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic(self):
        """test_apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params.
        Test with a filename provided in config.
        """
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted'),
               'filename': self.aptlistfile}
        self.apt_src_basic(self.aptlistfile, [cfg])

    def test_apt_src_basic_dict(self):
        """test_apt_src_basic_dict
        Test Fix deb source string, has to overwrite mirror conf in params.
        Test with a filename provided in config.
        Provided in a dictionary with filename being the key (new format)
        """
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
        contents = load_tfile_or_url(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile_or_url(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic_tri(self):
        """test_apt_src_basic_tri
        Test Fix three deb source string, has to overwrite mirror conf in
        params. Test with filenames provided in config.
        """
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
        """test_apt_src_basic_dict_tri
        Test Fix three deb source string, has to overwrite mirror conf in
        params. Test with filenames provided in config.
        Provided in a dictionary with filename being the key (new format)
        """
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
        """test_apt_src_basic_nofn
        Test Fix deb source string, has to overwrite mirror conf in params.
        Test without a filename provided in config and test for known fallback.
        """
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted')}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_basic(self.fallbackfn, [cfg])

    def apt_src_replacement(self, filename, cfg):
        """apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        cc_apt_configure.add_apt_sources(cfg, params)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace(self):
        """test_apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs with
        Filename being set
        """
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
        contents = load_tfile_or_url(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "main"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile_or_url(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "universe"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace_tri(self):
        """test_apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        Filename being set
        """
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        self.apt_src_replace_tri([cfg1, cfg2, cfg3])

    def test_apt_src_replace_dict_tri(self):
        """test_apt_src_replace_dict_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        Filename being set
        Provided in a dictionary with filename being the key (new format)
        We also test a new special conditions of the new format that allows
        filenames to be overwritten inside the directory entry.
        """
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused': {'source': 'deb $MIRROR $RELEASE main',
                           'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self.apt_src_replace_tri(cfg)

    def test_apt_src_replace_nofn(self):
        """test_apt_src_replace_nofn
        Test Autoreplacement of MIRROR and RELEASE in source specs with
        No filename being set
        """
        cfg = {'source': 'deb $MIRROR $RELEASE multiverse'}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_replacement(self.fallbackfn, [cfg])

    def apt_src_keyid(self, filename, cfg, keynum):
        """apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1234', '')) as mockobj:
            cc_apt_configure.add_apt_sources(cfg, params)

        # check if it added the right ammount of keys
        calls = []
        for _ in range(keynum):
            calls.append(call(('apt-key', 'add', '-'), 'fakekey 1234'))
        mockobj.assert_has_calls(calls, any_order=True)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyid(self):
        """test_apt_src_keyid
        Test specification of a source + keyid with filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'keyid': "03683F77",
               'filename': self.aptlistfile}
        self.apt_src_keyid(self.aptlistfile, [cfg], 1)

    def test_apt_src_keyid_tri(self):
        """test_apt_src_keyid_tri
        Test specification of a source + keyid with filename being set
        Setting three of such, check for content and keys
        """
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
        contents = load_tfile_or_url(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "universe"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile_or_url(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyid_nofn(self):
        """test_apt_src_keyid_nofn
        Test specification of a source + keyid without filename being set
        """
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
        params = self._get_default_params()

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_apt_sources([cfg], params)

        mockobj.assert_called_with(('apt-key', 'add', '-'), 'fakekey 4321')

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_key(self):
        """test_apt_src_key
        Test specification of a source + key with filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321",
               'filename': self.aptlistfile}
        self.apt_src_key(self.aptlistfile, cfg)

    def test_apt_src_key_nofn(self):
        """test_apt_src_key_nofn
        Test specification of a source + key without filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321"}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_src_key(self.fallbackfn, cfg)

    def test_apt_src_keyonly(self):
        """test_apt_src_keyonly
        Test specification key without source
        """
        params = self._get_default_params()
        cfg = {'key': "fakekey 4242",
               'filename': self.aptlistfile}

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_apt_sources([cfg], params)

        mockobj.assert_called_once_with(('apt-key', 'add', '-'),
                                        'fakekey 4242')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyidonly(self):
        """test_apt_src_keyidonly
        Test specification of a keyid without source
        """
        params = self._get_default_params()
        cfg = {'keyid': "03683F77",
               'filename': self.aptlistfile}

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            cc_apt_configure.add_apt_sources([cfg], params)

        mockobj.assert_called_with(('apt-key', 'add', '-'), 'fakekey 1212')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def apt_src_keyid_real(self, cfg, expectedkey):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        params = self._get_default_params()

        def fake_gpg_recv_key(key, keyserver):
            """try original gpg_recv_key, but allow fall back"""
            try:
                self.orig_gpg_recv_key(key, keyserver)
            except ValueError:
                # if this is a networking issue mock it's effect
                testsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    testsock.connect((keyserver, 80))
                    testsock.close()
                except socket.error:
                    # as fallback add the known key as a working recv would
                    util.subp(("gpg", "--import", "-"), EXPECTEDKEY,
                              capture=True)

        with mock.patch.object(cc_apt_configure, 'add_apt_key_raw') as mockkey:
            with mock.patch.object(util, 'gpg_recv_key',
                                   side_effect=fake_gpg_recv_key):
                cc_apt_configure.add_apt_sources([cfg], params)

        # no matter if really imported or faked, ensure we add the right key
        mockkey.assert_called_with(expectedkey)

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
        """test_apt_src_ppa
        Test specification of a ppa
        """
        params = self._get_default_params()
        cfg = {'source': 'ppa:smoser/cloud-init-test',
               'filename': self.aptlistfile}

        # default matcher needed for ppa
        matcher = re.compile(r'^[\w-]+:\w').search

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_apt_sources([cfg], params,
                                             aa_repo_match=matcher)
        mockobj.assert_called_once_with(['add-apt-repository',
                                         'ppa:smoser/cloud-init-test'])

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_ppa_tri(self):
        """test_apt_src_ppa_tri
        Test specification of a ppa
        """
        params = self._get_default_params()
        cfg1 = {'source': 'ppa:smoser/cloud-init-test',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'ppa:smoser/cloud-init-test2',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'ppa:smoser/cloud-init-test3',
                'filename': self.aptlistfile3}

        # default matcher needed for ppa
        matcher = re.compile(r'^[\w-]+:\w').search

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_apt_sources([cfg1, cfg2, cfg3], params,
                                             aa_repo_match=matcher)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test']),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2']),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'])]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))
        self.assertFalse(os.path.isfile(self.aptlistfile2))
        self.assertFalse(os.path.isfile(self.aptlistfile3))

    def test_convert_to_new_format(self):
        """test_convert_to_new_format
        Test the conversion of old to new format
        And the noop conversion of new to new format as well
        """
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        checkcfg = {self.aptlistfile: {'filename': self.aptlistfile,
                                       'source': 'deb $MIRROR $RELEASE '
                                                 'multiverse'},
                    self.aptlistfile2: {'filename': self.aptlistfile2,
                                        'source': 'deb $MIRROR $RELEASE main'},
                    self.aptlistfile3: {'filename': self.aptlistfile3,
                                        'source': 'deb $MIRROR $RELEASE '
                                                  'universe'}}

        newcfg = cc_apt_configure.convert_to_new_format([cfg1, cfg2, cfg3])
        self.assertEqual(newcfg, checkcfg)

        newcfg2 = cc_apt_configure.convert_to_new_format(newcfg)
        self.assertEqual(newcfg2, checkcfg)

        with self.assertRaises(ValueError):
            cc_apt_configure.convert_to_new_format(5)


# vi: ts=4 expandtab
