""" test_handler_apt_source
Testing various config variations of the apt_source config
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
from cloudinit import util

from ..helpers import TestCase

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
    """ load_tfile_or_url
    load file and return content after decoding
    """
    return util.decode_binary(util.read_file_or_url(*args, **kwargs).contents)


class TestAptSourceConfig(TestCase):
    """ TestAptSourceConfig
    Main Class to test apt_source configs
    """
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


    @staticmethod
    def _get_default_params():
        """ get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = cc_apt_configure.get_release()
        params['MIRROR'] = "http://archive.ubuntu.com/ubuntu"
        return params

    def myjoin(self, *args, **kwargs):
        """ myjoin - redir into writable tmpdir"""
        if (args[0] == "/etc/apt/sources.list.d/"
                and args[1] == "cloud_config_sources.list"
                and len(args) == 2):
            return self.join(self.tmp, args[0].lstrip("/"), args[1])
        else:
            return self.join(*args, **kwargs)

    def apt_source_basic(self, filename, cfg):
        """ apt_source_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        cc_apt_configure.add_sources(cfg, params)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_source_basic(self):
        """ test_apt_source_basic
        Test Fix deb source string, has to overwrite mirror conf in params.
        Test with a filename provided in config.
        """
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted'),
               'filename': self.aptlistfile}
        self.apt_source_basic(self.aptlistfile, [cfg])

    def test_apt_source_basic_triple(self):
        """ test_apt_source_basic_triple
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
        self.apt_source_basic(self.aptlistfile, [cfg1, cfg2, cfg3])

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

    def test_apt_source_basic_nofn(self):
        """ test_apt_source_basic_nofn
        Test Fix deb source string, has to overwrite mirror conf in params.
        Test without a filename provided in config and test for known fallback.
        """
        cfg = {'source': ('deb http://archive.ubuntu.com/ubuntu'
                          ' karmic-backports'
                          ' main universe multiverse restricted')}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_source_basic(self.fallbackfn, [cfg])

    def apt_source_replacement(self, filename, cfg):
        """ apt_source_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        cc_apt_configure.add_sources(cfg, params)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_source_replace(self):
        """ test_apt_source_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs with
        Filename being set
        """
        cfg = {'source': 'deb $MIRROR $RELEASE multiverse',
               'filename': self.aptlistfile}
        self.apt_source_replacement(self.aptlistfile, [cfg])

    def test_apt_source_replace_triple(self):
        """ test_apt_source_replace_triple
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        Filename being set
        """
        cfg1 = {'source': 'deb $MIRROR $RELEASE multiverse',
                'filename': self.aptlistfile}
        cfg2 = {'source': 'deb $MIRROR $RELEASE main',
                'filename': self.aptlistfile2}
        cfg3 = {'source': 'deb $MIRROR $RELEASE universe',
                'filename': self.aptlistfile3}
        self.apt_source_replacement(self.aptlistfile, [cfg1, cfg2, cfg3])

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


    def test_apt_source_replace_nofn(self):
        """ test_apt_source_replace_nofn
        Test Autoreplacement of MIRROR and RELEASE in source specs with
        No filename being set
        """
        cfg = {'source': 'deb $MIRROR $RELEASE multiverse'}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_source_replacement(self.fallbackfn, [cfg])

    def apt_source_keyid(self, filename, cfg, keynum):
        """ apt_source_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1234', '')) as mockobj:
            cc_apt_configure.add_sources(cfg, params)

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

    def test_apt_source_keyid(self):
        """ test_apt_source_keyid
        Test specification of a source + keyid with filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'keyid': "03683F77",
               'filename': self.aptlistfile}
        self.apt_source_keyid(self.aptlistfile, [cfg], 1)

    def test_apt_source_keyid_triple(self):
        """ test_apt_source_keyid_triple
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

        self.apt_source_keyid(self.aptlistfile, [cfg1, cfg2, cfg3], 3)
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

    def test_apt_source_keyid_nofn(self):
        """ test_apt_source_keyid_nofn
        Test specification of a source + keyid without filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'keyid': "03683F77"}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_source_keyid(self.fallbackfn, [cfg], 1)

    def apt_source_key(self, filename, cfg):
        """ apt_source_key
        Test specification of a source + key
        """
        params = self._get_default_params()

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_sources([cfg], params)

        mockobj.assert_called_with(('apt-key', 'add', '-'), 'fakekey 4321')

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile_or_url(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_source_key(self):
        """ test_apt_source_key
        Test specification of a source + key with filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321",
               'filename': self.aptlistfile}
        self.apt_source_key(self.aptlistfile, cfg)

    def test_apt_source_key_nofn(self):
        """ test_apt_source_key_nofn
        Test specification of a source + key without filename being set
        """
        cfg = {'source': ('deb '
                          'http://ppa.launchpad.net/'
                          'smoser/cloud-init-test/ubuntu'
                          ' xenial main'),
               'key': "fakekey 4321"}
        with mock.patch.object(os.path, 'join', side_effect=self.myjoin):
            self.apt_source_key(self.fallbackfn, cfg)

    def test_apt_source_keyonly(self):
        """ test_apt_source_keyonly
        Test specification key without source
        """
        params = self._get_default_params()
        cfg = {'key': "fakekey 4242",
               'filename': self.aptlistfile}

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_sources([cfg], params)

        mockobj.assert_called_once_with(('apt-key', 'add', '-'),
                                        'fakekey 4242')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_source_keyidonly(self):
        """ test_apt_source_keyidonly
        Test specification of a keyid without source
        """
        params = self._get_default_params()
        cfg = {'keyid': "03683F77",
               'filename': self.aptlistfile}

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            cc_apt_configure.add_sources([cfg], params)

        mockobj.assert_called_with(('apt-key', 'add', '-'), 'fakekey 1212')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_source_keyid_real(self):
        """ test_apt_source_keyid_real
        Test specification of a keyid without source incl
        up to addition of the key (nothing but add_key_raw mocked)
        """
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {'keyid': keyid,
               'filename': self.aptlistfile}

        with mock.patch.object(cc_apt_configure, 'add_key_raw') as mockobj:
            cc_apt_configure.add_sources([cfg], params)

        mockobj.assert_called_with(EXPECTEDKEY)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_source_longkeyid_real(self):
        """ test_apt_source_keyid_real
        Test specification of a long key fingerprint without source incl
        up to addition of the key (nothing but add_key_raw mocked)
        """
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        params = self._get_default_params()
        cfg = {'keyid': keyid,
               'filename': self.aptlistfile}

        with mock.patch.object(cc_apt_configure, 'add_key_raw') as mockobj:
            cc_apt_configure.add_sources([cfg], params)

        mockobj.assert_called_with(EXPECTEDKEY)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_source_ppa(self):
        """ test_apt_source_ppa
        Test specification of a ppa
        """
        params = self._get_default_params()
        cfg = {'source': 'ppa:smoser/cloud-init-test',
               'filename': self.aptlistfile}

        # default matcher needed for ppa
        matcher = re.compile(r'^[\w-]+:\w').search

        with mock.patch.object(util, 'subp') as mockobj:
            cc_apt_configure.add_sources([cfg], params, aa_repo_match=matcher)
        mockobj.assert_called_once_with(['add-apt-repository',
                                         'ppa:smoser/cloud-init-test'])

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))


# vi: ts=4 expandtab
