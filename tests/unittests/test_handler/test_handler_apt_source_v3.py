# This file is part of cloud-init. See LICENSE file for license information.

"""test_handler_apt_source_v3
Testing various config variations of the apt_source custom config
This tries to call all in the new v3 format and cares about new features
"""
import glob
import os
import re
import shutil
import socket
import tempfile

from unittest import TestCase

try:
    from unittest import mock
except ImportError:
    import mock
from mock import call

from cloudinit import cloud
from cloudinit import distros
from cloudinit import gpg
from cloudinit import helpers
from cloudinit import util

from cloudinit.config import cc_apt_configure
from cloudinit.sources import DataSourceNone

from cloudinit.tests import helpers as t_help

EXPECTEDKEY = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----
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

TARGET = None

MOCK_LSB_RELEASE_DATA = {
    'id': 'Ubuntu', 'description': 'Ubuntu 18.04.1 LTS',
    'release': '18.04', 'codename': 'bionic'}


class TestAptSourceConfig(t_help.FilesystemMockingTestCase):
    """TestAptSourceConfig
    Main Class to test apt configs
    """
    def setUp(self):
        super(TestAptSourceConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(shutil.rmtree, self.new_root)
        self.aptlistfile = os.path.join(self.tmp, "single-deb.list")
        self.aptlistfile2 = os.path.join(self.tmp, "single-deb2.list")
        self.aptlistfile3 = os.path.join(self.tmp, "single-deb3.list")
        self.join = os.path.join
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search
        self.add_patch(
            'cloudinit.config.cc_apt_configure.util.lsb_release',
            'm_lsb_release', return_value=MOCK_LSB_RELEASE_DATA.copy())

    @staticmethod
    def _add_apt_sources(*args, **kwargs):
        with mock.patch.object(cc_apt_configure, 'update_packages'):
            cc_apt_configure.add_apt_sources(*args, **kwargs)

    @staticmethod
    def _get_default_params():
        """get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = MOCK_LSB_RELEASE_DATA['release']
        arch = 'amd64'
        params['MIRROR'] = cc_apt_configure.\
            get_default_mirrors(arch)["PRIMARY"]
        return params

    def _myjoin(self, *args, **kwargs):
        """_myjoin - redir into writable tmpdir"""
        if (args[0] == "/etc/apt/sources.list.d/" and
                args[1] == "cloud_config_sources.list" and
                len(args) == 2):
            return self.join(self.tmp, args[0].lstrip("/"), args[1])
        else:
            return self.join(*args, **kwargs)

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    def _apt_src_basic(self, filename, cfg):
        """_apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        self._add_apt_sources(cfg, TARGET, template_params=params,
                              aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_v3_src_basic(self):
        """test_apt_v3_src_basic - Test fix deb source string"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

    def test_apt_v3_src_basic_tri(self):
        """test_apt_v3_src_basic_tri - Test multiple fix deb source strings"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')},
               self.aptlistfile2: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' precise-backports'
                                    ' main universe multiverse restricted')},
               self.aptlistfile3: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' lucid-backports'
                                    ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        contents = util.load_file(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = util.load_file(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def _apt_src_replacement(self, filename, cfg):
        """apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        self._add_apt_sources(cfg, TARGET, template_params=params,
                              aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_v3_src_replace(self):
        """test_apt_v3_src_replace - Test replacement of MIRROR & RELEASE"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'}}
        self._apt_src_replacement(self.aptlistfile, cfg)

    def test_apt_v3_src_replace_fn(self):
        """test_apt_v3_src_replace_fn - Test filename overwritten in dict"""
        cfg = {'ignored': {'source': 'deb $MIRROR $RELEASE multiverse',
                           'filename': self.aptlistfile}}
        # second file should overwrite the dict key
        self._apt_src_replacement(self.aptlistfile, cfg)

    def _apt_src_replace_tri(self, cfg):
        """_apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self._apt_src_replacement(self.aptlistfile, cfg)

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

    def test_apt_v3_src_replace_tri(self):
        """test_apt_v3_src_replace_tri - Test multiple replace/overwrites"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused': {'source': 'deb $MIRROR $RELEASE main',
                           'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self._apt_src_replace_tri(cfg)

    def _apt_src_keyid(self, filename, cfg, keynum):
        """_apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch("cloudinit.util.subp",
                        return_value=('fakekey 1234', '')) as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        # check if it added the right ammount of keys
        calls = []
        for _ in range(keynum):
            calls.append(call(['apt-key', 'add', '-'], data=b'fakekey 1234',
                              target=TARGET))
        mockobj.assert_has_calls(calls, any_order=True)

        self.assertTrue(os.path.isfile(filename))

        contents = util.load_file(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_v3_src_keyid(self):
        """test_apt_v3_src_keyid - Test source + keyid with filename"""
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"}}
        self._apt_src_keyid(self.aptlistfile, cfg, 1)

    def test_apt_v3_src_keyid_tri(self):
        """test_apt_v3_src_keyid_tri - Test multiple src+key+filen writes"""
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"},
               'ignored': {'source': ('deb '
                                      'http://ppa.launchpad.net/'
                                      'smoser/cloud-init-test/ubuntu'
                                      ' xenial universe'),
                           'keyid': "03683F77",
                           'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial multiverse'),
                                   'keyid': "03683F77"}}

        self._apt_src_keyid(self.aptlistfile, cfg, 3)
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

    def test_apt_v3_src_key(self):
        """test_apt_v3_src_key - Test source + key"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'key': "fakekey 4321"}}

        with mock.patch.object(util, 'subp') as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 4321',
                                target=TARGET)

        self.assertTrue(os.path.isfile(self.aptlistfile))

        contents = util.load_file(self.aptlistfile)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_v3_src_keyonly(self):
        """test_apt_v3_src_keyonly - Test key without source"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'key': "fakekey 4242"}}

        with mock.patch.object(util, 'subp') as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 4242',
                                target=TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_v3_src_keyidonly(self):
        """test_apt_v3_src_keyidonly - Test keyid without source"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': "03683F77"}}

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 1212',
                                target=TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def apt_src_keyid_real(self, cfg, expectedkey):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        params = self._get_default_params()

        with mock.patch.object(cc_apt_configure, 'add_apt_key_raw') as mockkey:
            with mock.patch.object(gpg, 'getkeybyid',
                                   return_value=expectedkey) as mockgetkey:
                self._add_apt_sources(cfg, TARGET, template_params=params,
                                      aa_repo_match=self.matcher)

        keycfg = cfg[self.aptlistfile]
        mockgetkey.assert_called_with(keycfg['keyid'],
                                      keycfg.get('keyserver',
                                                 'keyserver.ubuntu.com'))
        mockkey.assert_called_with(expectedkey, TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_v3_src_keyid_real(self):
        """test_apt_v3_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_v3_src_longkeyid_real(self):
        """test_apt_v3_src_longkeyid_real Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_v3_src_longkeyid_ks_real(self):
        """test_apt_v3_src_longkeyid_ks_real Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'keys.gnupg.net'}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_v3_src_keyid_keyserver(self):
        """test_apt_v3_src_keyid_keyserver - Test custom keyserver"""
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'test.random.com'}}

        # in some test environments only *.ubuntu.com is reachable
        # so mock the call and check if the config got there
        with mock.patch.object(gpg, 'getkeybyid',
                               return_value="fakekey") as mockgetkey:
            with mock.patch.object(cc_apt_configure,
                                   'add_apt_key_raw') as mockadd:
                self._add_apt_sources(cfg, TARGET, template_params=params,
                                      aa_repo_match=self.matcher)

        mockgetkey.assert_called_with('03683F77', 'test.random.com')
        mockadd.assert_called_with('fakekey', TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_v3_src_ppa(self):
        """test_apt_v3_src_ppa - Test specification of a ppa"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'}}

        with mock.patch("cloudinit.util.subp") as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)
        mockobj.assert_any_call(['add-apt-repository',
                                 'ppa:smoser/cloud-init-test'], target=TARGET)

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_v3_src_ppa_tri(self):
        """test_apt_v3_src_ppa_tri - Test specification of multiple ppa's"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'},
               self.aptlistfile2: {'source': 'ppa:smoser/cloud-init-test2'},
               self.aptlistfile3: {'source': 'ppa:smoser/cloud-init-test3'}}

        with mock.patch("cloudinit.util.subp") as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test'],
                      target=TARGET),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2'],
                      target=TARGET),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'],
                      target=TARGET)]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))
        self.assertFalse(os.path.isfile(self.aptlistfile2))
        self.assertFalse(os.path.isfile(self.aptlistfile3))

    @mock.patch("cloudinit.config.cc_apt_configure.util.get_architecture")
    def test_apt_v3_list_rename(self, m_get_architecture):
        """test_apt_v3_list_rename - Test find mirror and apt list renaming"""
        pre = "/var/lib/apt/lists"
        # filenames are archive dependent

        arch = 's390x'
        m_get_architecture.return_value = arch
        component = "ubuntu-ports"
        archive = "ports.ubuntu.com"

        cfg = {'primary': [{'arches': ["default"],
                            'uri':
                            'http://test.ubuntu.com/%s/' % component}],
               'security': [{'arches': ["default"],
                             'uri':
                             'http://testsec.ubuntu.com/%s/' % component}]}
        post = ("%s_dists_%s-updates_InRelease" %
                (component, MOCK_LSB_RELEASE_DATA['codename']))
        fromfn = ("%s/%s_%s" % (pre, archive, post))
        tofn = ("%s/test.ubuntu.com_%s" % (pre, post))

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None, arch)

        self.assertEqual(mirrors['MIRROR'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['PRIMARY'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['SECURITY'],
                         "http://testsec.ubuntu.com/%s/" % component)

        with mock.patch.object(os, 'rename') as mockren:
            with mock.patch.object(glob, 'glob',
                                   return_value=[fromfn]):
                cc_apt_configure.rename_apt_lists(mirrors, TARGET)

        mockren.assert_any_call(fromfn, tofn)

    @mock.patch("cloudinit.config.cc_apt_configure.util.get_architecture")
    def test_apt_v3_list_rename_non_slash(self, m_get_architecture):
        target = os.path.join(self.tmp, "rename_non_slash")
        apt_lists_d = os.path.join(target, "./" + cc_apt_configure.APT_LISTS)

        m_get_architecture.return_value = 'amd64'

        mirror_path = "some/random/path/"
        primary = "http://test.ubuntu.com/" + mirror_path
        security = "http://test-security.ubuntu.com/" + mirror_path
        mirrors = {'PRIMARY': primary, 'SECURITY': security}

        # these match default archive prefixes
        opri_pre = "archive.ubuntu.com_ubuntu_dists_xenial"
        osec_pre = "security.ubuntu.com_ubuntu_dists_xenial"
        # this one won't match and should not be renamed defaults.
        other_pre = "dl.google.com_linux_chrome_deb_dists_stable"
        # these are our new expected prefixes
        npri_pre = "test.ubuntu.com_some_random_path_dists_xenial"
        nsec_pre = "test-security.ubuntu.com_some_random_path_dists_xenial"

        files = [
            # orig prefix, new prefix, suffix
            (opri_pre, npri_pre, "_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "_main_binary-amd64_InRelease"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_InRelease"),
            (other_pre, other_pre, "_main_binary-amd64_Packages"),
            (other_pre, other_pre, "_Release"),
            (other_pre, other_pre, "_Release.gpg"),
            (osec_pre, nsec_pre, "_InRelease"),
            (osec_pre, nsec_pre, "_main_binary-amd64_Packages"),
            (osec_pre, nsec_pre, "_universe_binary-amd64_Packages"),
        ]

        expected = sorted([npre + suff for opre, npre, suff in files])
        # create files
        for (opre, _npre, suff) in files:
            fpath = os.path.join(apt_lists_d, opre + suff)
            util.write_file(fpath, content=fpath)

        cc_apt_configure.rename_apt_lists(mirrors, target)
        found = sorted(os.listdir(apt_lists_d))
        self.assertEqual(expected, found)

    @staticmethod
    def test_apt_v3_proxy():
        """test_apt_v3_proxy - Test apt_*proxy configuration"""
        cfg = {"proxy": "foobar1",
               "http_proxy": "foobar2",
               "ftp_proxy": "foobar3",
               "https_proxy": "foobar4"}

        with mock.patch.object(util, 'write_file') as mockobj:
            cc_apt_configure.apply_apt_config(cfg, "proxyfn", "notused")

        mockobj.assert_called_with('proxyfn',
                                   ('Acquire::http::Proxy "foobar1";\n'
                                    'Acquire::http::Proxy "foobar2";\n'
                                    'Acquire::ftp::Proxy "foobar3";\n'
                                    'Acquire::https::Proxy "foobar4";\n'))

    def test_apt_v3_mirror(self):
        """test_apt_v3_mirror - Test defining a mirror"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir}],
               "security": [{'arches': ["default"],
                             "uri": smir}]}

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_apt_v3_mirror_default(self):
        """test_apt_v3_mirror_default - Test without defining a mirror"""
        arch = 'amd64'
        default_mirrors = cc_apt_configure.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mycloud = self._get_cloud('ubuntu')
        mirrors = cc_apt_configure.find_apt_mirror_info({}, mycloud, arch)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_apt_v3_mirror_arches(self):
        """test_apt_v3_mirror_arches - Test arches selection of mirror"""
        pmir = "http://my-primary.ubuntu.com/ubuntu/"
        smir = "http://my-security.ubuntu.com/ubuntu/"
        arch = 'ppc64el'
        cfg = {"primary": [{'arches': ["default"], "uri": "notthis-primary"},
                           {'arches': [arch], "uri": pmir}],
               "security": [{'arches': ["default"], "uri": "nothis-security"},
                            {'arches': [arch], "uri": smir}]}

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None, arch)

        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_apt_v3_mirror_arches_default(self):
        """test_apt_v3_mirror_arches - Test falling back to default arch"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthis"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["default"],
                             "uri": smir}]}

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    @mock.patch("cloudinit.config.cc_apt_configure.util.get_architecture")
    def test_apt_v3_get_def_mir_non_intel_no_arch(self, m_get_architecture):
        arch = 'ppc64el'
        m_get_architecture.return_value = arch
        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, cc_apt_configure.get_default_mirrors())

    def test_apt_v3_get_default_mirrors_non_intel_with_arch(self):
        found = cc_apt_configure.get_default_mirrors('ppc64el')

        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, found)

    def test_apt_v3_mirror_arches_sysdefault(self):
        """test_apt_v3_mirror_arches - Test arches fallback to sys default"""
        arch = 'amd64'
        default_mirrors = cc_apt_configure.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mycloud = self._get_cloud('ubuntu')
        cfg = {"primary": [{'arches': ["thisarchdoesntexist_64"],
                            "uri": "notthis"},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthiseither"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["thisarchdoesntexist_64"],
                             "uri": "nothateither"}]}

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)

        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_apt_v3_mirror_search(self):
        """test_apt_v3_mirror_search - Test searching mirrors in a list
            mock checks to avoid relying on network connectivity"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "search": ["pfailme", pmir]}],
               "security": [{'arches': ["default"],
                             "search": ["sfailme", smir]}]}

        with mock.patch.object(cc_apt_configure, 'search_for_mirror',
                               side_effect=[pmir, smir]) as mocksearch:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None,
                                                            'amd64')

        calls = [call(["pfailme", pmir]),
                 call(["sfailme", smir])]
        mocksearch.assert_has_calls(calls)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_apt_v3_mirror_search_many2(self):
        """test_apt_v3_mirror_search_many3 - Test both mirrors specs at once"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir,
                            "search": ["pfailme", "foo"]}],
               "security": [{'arches': ["default"],
                             "uri": smir,
                             "search": ["sfailme", "bar"]}]}

        arch = 'amd64'

        # should be called only once per type, despite two mirror configs
        mycloud = None
        with mock.patch.object(cc_apt_configure, 'get_mirror',
                               return_value="http://mocked/foo") as mockgm:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [call(cfg, 'primary', arch, mycloud),
                 call(cfg, 'security', arch, mycloud)]
        mockgm.assert_has_calls(calls)

        # should not be called, since primary is specified
        with mock.patch.object(cc_apt_configure,
                               'search_for_mirror') as mockse:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, None, arch)
        mockse.assert_not_called()

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_apt_v3_url_resolvable(self):
        """test_apt_v3_url_resolvable - Test resolving urls"""

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mockresolve.assert_called_with("1.2.3.4")

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
        mockresolve.assert_called_with("us.archive.ubuntu.com")

        # former tests can leave this set (or not if the test is ran directly)
        # do a hard reset to ensure a stable result
        util._DNS_REDIRECT_IP = None
        bad = [(None, None, None, "badname", ["10.3.2.1"])]
        good = [(None, None, None, "goodname", ["10.2.3.4"])]
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad, bad, bad, good,
                                            good]) as mocksock:
            ret = util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
            ret2 = util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mocksock.assert_any_call('does-not-exist.example.com.', None,
                                 0, 0, 1, 2)
        mocksock.assert_any_call('example.invalid.', None, 0, 0, 1, 2)
        mocksock.assert_any_call('us.archive.ubuntu.com', None)
        mocksock.assert_any_call('1.2.3.4', None)

        self.assertTrue(ret)
        self.assertTrue(ret2)

        # side effect need only bad ret after initial call
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad]) as mocksock:
            ret3 = util.is_resolvable_url("http://failme.com/ubuntu")
        calls = [call('failme.com', None)]
        mocksock.assert_has_calls(calls)
        self.assertFalse(ret3)

    def test_apt_v3_disable_suites(self):
        """test_disable_suites - disable_suites with many configurations"""
        release = "xenial"
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""

        # disable nothing
        disabled = []
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable release suite
        disabled = ["$RELEASE"]
        expect = """\
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable other suite
        disabled = ["$RELEASE-updates"]
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu"""
                  """ xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # multi disable
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # multi line disable (same suite multiple times in input)
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
# suite disabled by cloud-init: deb http://UBUNTU.com//ubuntu """
                  """xenial-updates main
# suite disabled by cloud-init: deb http://UBUNTU.COM//ubuntu """
                  """xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # comment in input
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
#deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
#deb http://UBUNTU.com//ubuntu xenial-updates main
# suite disabled by cloud-init: deb http://UBUNTU.COM//ubuntu """
                  """xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable custom suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ foobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
# suite disabled by cloud-init: deb http://ubuntu.com/ubuntu/ foobar main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable non existing suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable suite with option
        disabled = ["$RELEASE-updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb [a=b] http://ubu.com//ubu """
                  """xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable suite with more options and auto $RELEASE expansion
        disabled = ["updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b c=d] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb [a=b c=d] \
http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

        # single disable suite while options at others
        disabled = ["$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = ("""deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
                  """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main""")
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        self.assertEqual(expect, result)

    def test_disable_suites_blank_lines(self):
        """test_disable_suites_blank_lines - ensure blank lines allowed"""
        lines = ["deb %(repo)s %(rel)s main universe",
                 "",
                 "deb %(repo)s %(rel)s-updates main universe",
                 "   # random comment",
                 "#comment here",
                 ""]
        rel = "trusty"
        repo = 'http://example.com/mirrors/ubuntu'
        orig = "\n".join(lines) % {'repo': repo, 'rel': rel}
        self.assertEqual(
            orig, cc_apt_configure.disable_suites(["proposed"], orig, rel))

    @mock.patch("cloudinit.util.get_hostname", return_value='abc.localdomain')
    def test_apt_v3_mirror_search_dns(self, m_get_hostname):
        """test_apt_v3_mirror_search_dns - Test searching dns patterns"""
        pmir = "phit"
        smir = "shit"
        arch = 'amd64'
        mycloud = self._get_cloud('ubuntu')
        cfg = {"primary": [{'arches': ["default"],
                            "search_dns": True}],
               "security": [{'arches': ["default"],
                             "search_dns": True}]}

        with mock.patch.object(cc_apt_configure, 'get_mirror',
                               return_value="http://mocked/foo") as mockgm:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [call(cfg, 'primary', arch, mycloud),
                 call(cfg, 'security', arch, mycloud)]
        mockgm.assert_has_calls(calls)

        with mock.patch.object(cc_apt_configure, 'search_for_mirror_dns',
                               return_value="http://mocked/foo") as mocksdns:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [call(True, 'primary', cfg, mycloud),
                 call(True, 'security', cfg, mycloud)]
        mocksdns.assert_has_calls(calls)

        # first return is for the non-dns call before
        with mock.patch.object(cc_apt_configure, 'search_for_mirror',
                               side_effect=[None, pmir, None, smir]) as mockse:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)

        calls = [call(None),
                 call(['http://ubuntu-mirror.localdomain/ubuntu',
                       'http://ubuntu-mirror/ubuntu']),
                 call(None),
                 call(['http://ubuntu-security-mirror.localdomain/ubuntu',
                       'http://ubuntu-security-mirror/ubuntu'])]
        mockse.assert_has_calls(calls)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)


class TestDebconfSelections(TestCase):

    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    def test_no_set_sel_if_none_to_set(self, m_set_sel):
        cc_apt_configure.apply_debconf_selections({'foo': 'bar'})
        m_set_sel.assert_not_called()

    @mock.patch("cloudinit.config.cc_apt_configure."
                "debconf_set_selections")
    @mock.patch("cloudinit.config.cc_apt_configure."
                "util.get_installed_packages")
    def test_set_sel_call_has_expected_input(self, m_get_inst, m_set_sel):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1')}
        lines = '\n'.join(data.values()).split('\n')

        m_get_inst.return_value = ["adduser", "apparmor"]
        m_set_sel.return_value = None

        cc_apt_configure.apply_debconf_selections({'debconf_selections': data})
        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_set_sel.call_count, 1)

        # assumes called with *args value.
        selections = m_set_sel.call_args_list[0][0][0].decode()

        missing = [l for l in lines if l not in selections.splitlines()]
        self.assertEqual([], missing)

    @mock.patch("cloudinit.config.cc_apt_configure.dpkg_reconfigure")
    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    @mock.patch("cloudinit.config.cc_apt_configure."
                "util.get_installed_packages")
    def test_reconfigure_if_intersection(self, m_get_inst, m_set_sel,
                                         m_dpkg_r):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1'),
            'cloud-init': ('cloud-init cloud-init/datasources'
                           'multiselect MAAS')}

        m_set_sel.return_value = None
        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']

        cc_apt_configure.apply_debconf_selections({'debconf_selections': data})

        # reconfigure should be called with the intersection
        # of (packages in config, packages installed)
        self.assertEqual(m_dpkg_r.call_count, 1)
        # assumes called with *args (dpkg_reconfigure([a,b,c], target=))
        packages = m_dpkg_r.call_args_list[0][0][0]
        self.assertEqual(set(['cloud-init', 'pkgb']), set(packages))

    @mock.patch("cloudinit.config.cc_apt_configure.dpkg_reconfigure")
    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    @mock.patch("cloudinit.config.cc_apt_configure."
                "util.get_installed_packages")
    def test_reconfigure_if_no_intersection(self, m_get_inst, m_set_sel,
                                            m_dpkg_r):
        data = {'set1': 'pkga pkga/q1 mybool false'}

        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']
        m_set_sel.return_value = None

        cc_apt_configure.apply_debconf_selections({'debconf_selections': data})

        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_dpkg_r.call_count, 0)

    @mock.patch("cloudinit.config.cc_apt_configure.util.subp")
    def test_dpkg_reconfigure_does_reconfigure(self, m_subp):
        target = "/foo-target"

        # due to the way the cleaners are called (via dictionary reference)
        # mocking clean_cloud_init directly does not work.  So we mock
        # the CONFIG_CLEANERS dictionary and assert our cleaner is called.
        ci_cleaner = mock.MagicMock()
        with mock.patch.dict(("cloudinit.config.cc_apt_configure."
                              "CONFIG_CLEANERS"),
                             values={'cloud-init': ci_cleaner}, clear=True):
            cc_apt_configure.dpkg_reconfigure(['pkga', 'cloud-init'],
                                              target=target)
        # cloud-init is actually the only package we have a cleaner for
        # so for now, its the only one that should reconfigured
        self.assertTrue(m_subp.called)
        ci_cleaner.assert_called_with(target)
        self.assertEqual(m_subp.call_count, 1)
        found = m_subp.call_args_list[0][0][0]
        expected = ['dpkg-reconfigure', '--frontend=noninteractive',
                    'cloud-init']
        self.assertEqual(expected, found)

    @mock.patch("cloudinit.config.cc_apt_configure.util.subp")
    def test_dpkg_reconfigure_not_done_on_no_data(self, m_subp):
        cc_apt_configure.dpkg_reconfigure([])
        m_subp.assert_not_called()

    @mock.patch("cloudinit.config.cc_apt_configure.util.subp")
    def test_dpkg_reconfigure_not_done_if_no_cleaners(self, m_subp):
        cc_apt_configure.dpkg_reconfigure(['pkgfoo', 'pkgbar'])
        m_subp.assert_not_called()

#
# vi: ts=4 expandtab
