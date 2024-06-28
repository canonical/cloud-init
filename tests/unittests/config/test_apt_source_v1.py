# This file is part of cloud-init. See LICENSE file for license information.

"""test_handler_apt_source_v1
Testing various config variations of the apt_source config
This calls all things with v1 format to stress the conversion code on top of
the actually tested code.
"""
import os
import pathlib
import re
from functools import partial
from textwrap import dedent
from unittest import mock
from unittest.mock import call

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from cloudinit.subp import SubpResult
from tests.unittests.util import get_cloud

original_join = os.path.join

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


class FakeDistro:
    """Fake Distro helper object"""

    def update_package_sources(self, *, force=False):
        """Fake update_package_sources helper method"""
        return


class TestAptSourceConfig:
    """TestAptSourceConfig
    Main Class to test apt_source configs
    """

    release = "fantastic"
    matcher = re.compile(ADD_APT_REPO_MATCH).search

    @pytest.fixture
    def apt_lists(self, tmpdir):
        p1 = os.path.join(tmpdir, "single-deb.list")
        p2 = os.path.join(tmpdir, "single-deb2.list")
        p3 = os.path.join(tmpdir, "single-deb3.list")
        return p1, p2, p3

    @pytest.fixture
    def fallback_path(self, tmpdir):
        return os.path.join(
            tmpdir, "etc/apt/sources.list.d/", "cloud_config_sources.list"
        )

    @pytest.fixture(autouse=True)
    def common_mocks(self, mocker):
        mocker.patch(
            "cloudinit.util.lsb_release",
            return_value={"codename": self.release},
        )
        mocker.patch(
            "cloudinit.util.get_dpkg_architecture", return_value="amd64"
        )
        mocker.patch.object(
            subp, "subp", return_value=SubpResult("PPID   PID", "")
        )
        mocker.patch("cloudinit.config.cc_apt_configure._ensure_dependencies")

    def _get_default_params(self):
        """get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        return {
            "RELEASE": self.release,
            "MIRROR": "http://archive.ubuntu.com/ubuntu",
        }

    def wrapv1conf(self, cfg):
        params = self._get_default_params()
        # old v1 list format under old keys, but callabe to main handler
        # disable source.list rendering and set mirror to avoid other code
        return {
            "apt_preserve_sources_list": True,
            "apt_mirror": params["MIRROR"],
            "apt_sources": cfg,
        }

    def myjoin(self, tmpfile, *args, **kwargs):
        """myjoin - redir into writable tmpdir"""
        if (
            args[0] == "/etc/apt/sources.list.d/"
            and args[1] == "cloud_config_sources.list"
            and len(args) == 2
        ):
            return original_join(tmpfile, args[0].lstrip("/"), args[1])
        else:
            return original_join(*args, **kwargs)

    def apt_src_basic(self, filename, cfg, gpg):
        """apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        cfg = self.wrapv1conf(cfg)

        with mock.patch.object(cc_apt_configure, "GPG") as my_gpg:
            my_gpg.return_value = gpg
            cc_apt_configure.handle("test", cfg, get_cloud(), [])

        assert os.path.isfile(filename)

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://archive.ubuntu.com/ubuntu",
                "karmic-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_basic(self, apt_lists, m_gpg):
        """Test deb source string, overwrite mirror and filename"""
        cfg = {
            "source": (
                "deb http://archive.ubuntu.com/ubuntu"
                " karmic-backports"
                " main universe multiverse restricted"
            ),
            "filename": apt_lists[0],
        }
        self.apt_src_basic(apt_lists[0], [cfg], m_gpg)

    def test_apt_src_basic_dict(self, apt_lists, m_gpg):
        """Test deb source string, overwrite mirror and filename (dict)"""
        cfg = {
            apt_lists[0]: {
                "source": (
                    "deb http://archive.ubuntu.com/ubuntu"
                    " karmic-backports"
                    " main universe multiverse restricted"
                )
            }
        }
        self.apt_src_basic(apt_lists[0], cfg, m_gpg)

    def apt_src_basic_tri(self, cfg, apt_lists, m_gpg):
        """apt_src_basic_tri
        Test Fix three deb source string, has to overwrite mirror conf in
        params. Test with filenames provided in config.
        generic part to check three files with different content
        """
        self.apt_src_basic(apt_lists[0], cfg, m_gpg)

        # extra verify on two extra files of this test
        contents = util.load_text_file(apt_lists[1])
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://archive.ubuntu.com/ubuntu",
                "precise-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        )
        contents = util.load_text_file(apt_lists[2])
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://archive.ubuntu.com/ubuntu",
                "lucid-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_basic_tri(self, apt_lists, m_gpg):
        """Test Fix three deb source string with filenames"""
        cfg1 = {
            "source": (
                "deb http://archive.ubuntu.com/ubuntu"
                " karmic-backports"
                " main universe multiverse restricted"
            ),
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": (
                "deb http://archive.ubuntu.com/ubuntu"
                " precise-backports"
                " main universe multiverse restricted"
            ),
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": (
                "deb http://archive.ubuntu.com/ubuntu"
                " lucid-backports"
                " main universe multiverse restricted"
            ),
            "filename": apt_lists[2],
        }
        self.apt_src_basic_tri([cfg1, cfg2, cfg3], apt_lists, m_gpg)

    def test_apt_src_basic_dict_tri(self, apt_lists, m_gpg):
        """Test Fix three deb source string with filenames (dict)"""
        cfg = {
            apt_lists[0]: {
                "source": (
                    "deb http://archive.ubuntu.com/ubuntu"
                    " karmic-backports"
                    " main universe multiverse restricted"
                )
            },
            apt_lists[1]: {
                "source": (
                    "deb http://archive.ubuntu.com/ubuntu"
                    " precise-backports"
                    " main universe multiverse restricted"
                )
            },
            apt_lists[2]: {
                "source": (
                    "deb http://archive.ubuntu.com/ubuntu"
                    " lucid-backports"
                    " main universe multiverse restricted"
                )
            },
        }
        self.apt_src_basic_tri(cfg, apt_lists, m_gpg)

    def test_apt_src_basic_nofn(self, fallback_path, tmpdir, m_gpg):
        """Test Fix three deb source string without filenames (dict)"""
        cfg = {
            "source": (
                "deb http://archive.ubuntu.com/ubuntu"
                " karmic-backports"
                " main universe multiverse restricted"
            )
        }
        with mock.patch.object(
            os.path, "join", side_effect=partial(self.myjoin, tmpdir)
        ):
            self.apt_src_basic(fallback_path, [cfg], m_gpg)

    def apt_src_replacement(self, filename, cfg):
        """apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        cfg = self.wrapv1conf(cfg)
        params = self._get_default_params()
        cc_apt_configure.handle("test", cfg, get_cloud(), [])

        assert os.path.isfile(filename)

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "multiverse"),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_replace(self, apt_lists):
        """Test Autoreplacement of MIRROR and RELEASE in source specs"""
        cfg = {
            "source": "deb $MIRROR $RELEASE multiverse",
            "filename": apt_lists[0],
        }
        self.apt_src_replacement(apt_lists[0], [cfg])

    def apt_src_replace_tri(self, cfg, apt_lists):
        """apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self.apt_src_replacement(apt_lists[0], cfg)

        # extra verify on two extra files of this test
        params = self._get_default_params()
        contents = util.load_text_file(apt_lists[1])
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "main"),
            contents,
            flags=re.IGNORECASE,
        )

        contents = util.load_text_file(apt_lists[2])
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "universe"),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_replace_tri(self, apt_lists):
        """Test triple Autoreplacement of MIRROR and RELEASE in source specs"""
        cfg1 = {
            "source": "deb $MIRROR $RELEASE multiverse",
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": "deb $MIRROR $RELEASE main",
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": "deb $MIRROR $RELEASE universe",
            "filename": apt_lists[2],
        }
        self.apt_src_replace_tri([cfg1, cfg2, cfg3], apt_lists)

    def test_apt_src_replace_dict_tri(self, apt_lists):
        """Test triple Autoreplacement in source specs (dict)"""
        cfg = {
            apt_lists[0]: {"source": "deb $MIRROR $RELEASE multiverse"},
            "notused": {
                "source": "deb $MIRROR $RELEASE main",
                "filename": apt_lists[1],
            },
            apt_lists[2]: {"source": "deb $MIRROR $RELEASE universe"},
        }
        self.apt_src_replace_tri(cfg, apt_lists)

    def test_apt_src_replace_nofn(self, fallback_path, tmpdir):
        """Test Autoreplacement of MIRROR and RELEASE in source specs nofile"""
        cfg = {"source": "deb $MIRROR $RELEASE multiverse"}
        with mock.patch.object(
            os.path, "join", side_effect=partial(self.myjoin, tmpdir)
        ):
            self.apt_src_replacement(fallback_path, [cfg])

    def apt_src_keyid(self, filename, cfg, keynum, gpg):
        """apt_src_keyid
        Test specification of a source + keyid
        """
        cfg = self.wrapv1conf(cfg)
        cloud = get_cloud()

        with mock.patch.object(
            cc_apt_configure, "GPG"
        ) as this_gpg, mock.patch.object(
            cc_apt_configure, "add_apt_key"
        ) as mockobj:
            this_gpg.return_value = gpg
            cc_apt_configure.handle("test", cfg, cloud, [])

        # check if it added the right number of keys
        calls = []
        sources = cfg["apt"]["sources"]
        for src in sources:
            print(sources[src])
            calls.append(call(sources[src], cloud, gpg))

        mockobj.assert_has_calls(calls, any_order=True)

        assert os.path.isfile(filename)

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://ppa.launchpad.net/smoser/cloud-init-test/ubuntu",
                "xenial",
                "main",
            ),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_keyid(self, apt_lists, m_gpg):
        """Test specification of a source + keyid with filename being set"""
        cfg = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial main"
            ),
            "keyid": "03683F77",
            "filename": apt_lists[0],
        }
        self.apt_src_keyid(apt_lists[0], [cfg], 1, m_gpg)

    def test_apt_src_keyid_tri(self, apt_lists, m_gpg):
        """Test 3x specification of a source + keyid with filename being set"""
        cfg1 = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial main"
            ),
            "keyid": "03683F77",
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial universe"
            ),
            "keyid": "03683F77",
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial multiverse"
            ),
            "keyid": "03683F77",
            "filename": apt_lists[2],
        }

        self.apt_src_keyid(apt_lists[0], [cfg1, cfg2, cfg3], 3, m_gpg)
        contents = util.load_text_file(apt_lists[1])
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://ppa.launchpad.net/smoser/cloud-init-test/ubuntu",
                "xenial",
                "universe",
            ),
            contents,
            flags=re.IGNORECASE,
        )
        contents = util.load_text_file(apt_lists[2])
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://ppa.launchpad.net/smoser/cloud-init-test/ubuntu",
                "xenial",
                "multiverse",
            ),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_keyid_nofn(self, fallback_path, tmpdir, m_gpg):
        """Test specification of a source + keyid without filename being set"""
        cfg = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial main"
            ),
            "keyid": "03683F77",
        }
        with mock.patch.object(
            os.path, "join", side_effect=partial(self.myjoin, tmpdir)
        ):
            self.apt_src_keyid(fallback_path, [cfg], 1, m_gpg)

    def apt_src_key(self, filename, cfg, gpg):
        """apt_src_key
        Test specification of a source + key
        """
        cfg = self.wrapv1conf([cfg])
        cloud = get_cloud()

        with mock.patch.object(
            cc_apt_configure, "GPG"
        ) as this_gpg, mock.patch.object(
            cc_apt_configure, "add_apt_key"
        ) as mockobj:
            this_gpg.return_value = gpg
            cc_apt_configure.handle("test", cfg, cloud, [])

        # check if it added the right amount of keys
        sources = cfg["apt"]["sources"]
        calls = []
        for src in sources:
            calls.append(call(sources[src], cloud, gpg))

        mockobj.assert_has_calls(calls, any_order=True)

        assert os.path.isfile(filename)

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://ppa.launchpad.net/smoser/cloud-init-test/ubuntu",
                "xenial",
                "main",
            ),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_src_key(self, apt_lists, m_gpg):
        """Test specification of a source + key with filename being set"""
        cfg = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial main"
            ),
            "key": "fakekey 4321",
            "filename": apt_lists[0],
        }
        self.apt_src_key(apt_lists[0], cfg, m_gpg)

    def test_apt_src_key_nofn(self, fallback_path, tmpdir, m_gpg):
        """Test specification of a source + key without filename being set"""
        cfg = {
            "source": (
                "deb "
                "http://ppa.launchpad.net/"
                "smoser/cloud-init-test/ubuntu"
                " xenial main"
            ),
            "key": "fakekey 4321",
        }
        with mock.patch.object(
            os.path, "join", side_effect=partial(self.myjoin, tmpdir)
        ):
            self.apt_src_key(fallback_path, cfg, m_gpg)

    def test_apt_src_keyonly(self, apt_lists, m_gpg):
        """Test specifying key without source"""
        cfg = {"key": "fakekey 4242", "filename": apt_lists[0]}
        cfg = self.wrapv1conf([cfg])
        with mock.patch.object(
            cc_apt_configure, "GPG"
        ) as gpg, mock.patch.object(cc_apt_configure, "apt_key") as mockobj:
            gpg.return_value = m_gpg
            cc_apt_configure.handle("test", cfg, get_cloud(), [])

        calls = (
            call(
                "add",
                m_gpg,
                output_file=pathlib.Path(apt_lists[0]).stem,
                data="fakekey 4242",
                hardened=False,
            ),
        )
        mockobj.assert_has_calls(calls, any_order=True)

        # filename should be ignored on key only
        assert not os.path.isfile(apt_lists[0])

    def test_apt_src_keyidonly(self, apt_lists, m_gpg):
        """Test specification of a keyid without source"""
        cfg = {"keyid": "03683F77", "filename": apt_lists[0]}
        cfg = self.wrapv1conf([cfg])
        m_gpg.getkeybyid = mock.Mock(return_value="fakekey 1212")
        SAMPLE_GPG_AGENT_DIRMNGR_PIDS = dedent(
            """\
           PPID     PID
              1    1057
              1    1095
           1511    2493
           1511    2509
           """
        )
        with mock.patch.object(
            subp,
            "subp",
            side_effect=[
                SubpResult("fakekey 1212", ""),
                SubpResult(SAMPLE_GPG_AGENT_DIRMNGR_PIDS, ""),
            ],
        ), mock.patch.object(
            cc_apt_configure, "GPG"
        ) as gpg, mock.patch.object(
            cc_apt_configure, "apt_key"
        ) as mockobj:
            gpg.return_value = m_gpg
            cc_apt_configure.handle("test", cfg, get_cloud(), [])

        calls = (
            call(
                "add",
                m_gpg,
                output_file=pathlib.Path(apt_lists[0]).stem,
                data="fakekey 1212",
                hardened=False,
            ),
        )
        mockobj.assert_has_calls(calls, any_order=True)

        # filename should be ignored on key only
        assert not os.path.isfile(apt_lists[0])

    def apt_src_keyid_real(
        self, apt_lists, cfg, expectedkey, gpg, is_hardened=None
    ):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        cfg = self.wrapv1conf([cfg])
        gpg.getkeybyid = mock.Mock(return_value=expectedkey)

        with mock.patch.object(cc_apt_configure, "add_apt_key_raw") as mockkey:
            with mock.patch.object(cc_apt_configure, "GPG") as my_gpg:
                my_gpg.return_value = gpg
                cc_apt_configure.handle("test", cfg, get_cloud(), [])
        if is_hardened is not None:
            mockkey.assert_called_with(
                expectedkey, apt_lists[0], gpg, hardened=is_hardened
            )
        else:
            mockkey.assert_called_with(expectedkey, apt_lists[0], gpg)

        # filename should be ignored on key only
        assert not os.path.isfile(apt_lists[0])

    def test_apt_src_keyid_real(self, apt_lists, m_gpg):
        """test_apt_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {"keyid": keyid, "filename": apt_lists[0]}

        self.apt_src_keyid_real(
            apt_lists, cfg, EXPECTEDKEY, m_gpg, is_hardened=False
        )

    def test_apt_src_longkeyid_real(self, apt_lists, m_gpg):
        """test_apt_src_longkeyid_real - Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {"keyid": keyid, "filename": apt_lists[0]}

        self.apt_src_keyid_real(
            apt_lists, cfg, EXPECTEDKEY, m_gpg, is_hardened=False
        )

    def test_apt_src_longkeyid_ks_real(self, apt_lists, m_gpg):
        """test_apt_src_longkeyid_ks_real - Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {
            "keyid": keyid,
            "keyserver": "keys.gnupg.net",
            "filename": apt_lists[0],
        }

        self.apt_src_keyid_real(
            apt_lists, cfg, EXPECTEDKEY, m_gpg, is_hardened=False
        )

    def test_apt_src_ppa(self, apt_lists, mocker, m_gpg):
        """Test adding a ppa"""
        m_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult("PPID   PID", "")
        )
        mocker.patch("cloudinit.gpg.subp.which", return_value=False)
        cfg = {
            "source": "ppa:smoser/cloud-init-test",
            "filename": apt_lists[0],
        }
        cfg = self.wrapv1conf([cfg])

        with mock.patch.object(cc_apt_configure, "GPG") as my_gpg:
            my_gpg.return_value = m_gpg
            cc_apt_configure.handle("test", cfg, get_cloud(), [])
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "add-apt-repository",
                    "--no-update",
                    "ppa:smoser/cloud-init-test",
                ],
            ),
        ]
        # adding ppa should ignore filename (uses add-apt-repository)
        assert not os.path.isfile(apt_lists[0])

    def test_apt_src_ppa_tri(self, apt_lists, m_gpg):
        """Test adding three ppa's"""
        cfg1 = {
            "source": "ppa:smoser/cloud-init-test",
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": "ppa:smoser/cloud-init-test2",
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": "ppa:smoser/cloud-init-test3",
            "filename": apt_lists[2],
        }
        cfg = self.wrapv1conf([cfg1, cfg2, cfg3])

        with mock.patch.object(
            subp, "subp", return_value=SubpResult("PPID   PID", "")
        ) as mockobj:
            with mock.patch.object(cc_apt_configure, "GPG") as my_gpg:
                my_gpg.return_value = m_gpg
                cc_apt_configure.handle("test", cfg, get_cloud(), [])
        calls = [
            call(
                [
                    "add-apt-repository",
                    "--no-update",
                    "ppa:smoser/cloud-init-test",
                ],
            ),
            call(
                [
                    "add-apt-repository",
                    "--no-update",
                    "ppa:smoser/cloud-init-test2",
                ],
            ),
            call(
                [
                    "add-apt-repository",
                    "--no-update",
                    "ppa:smoser/cloud-init-test3",
                ],
            ),
        ]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        assert not os.path.isfile(apt_lists[0])
        assert not os.path.isfile(apt_lists[1])
        assert not os.path.isfile(apt_lists[2])

    def test_convert_to_new_format(self, apt_lists):
        """Test the conversion of old to new format"""
        cfg1 = {
            "source": "deb $MIRROR $RELEASE multiverse",
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": "deb $MIRROR $RELEASE main",
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": "deb $MIRROR $RELEASE universe",
            "filename": apt_lists[2],
        }
        cfg = {"apt_sources": [cfg1, cfg2, cfg3]}
        checkcfg = {
            apt_lists[0]: {
                "filename": apt_lists[0],
                "source": "deb $MIRROR $RELEASE multiverse",
            },
            apt_lists[1]: {
                "filename": apt_lists[1],
                "source": "deb $MIRROR $RELEASE main",
            },
            apt_lists[2]: {
                "filename": apt_lists[2],
                "source": "deb $MIRROR $RELEASE universe",
            },
        }

        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg)
        assert newcfg["apt"]["sources"] == checkcfg

        # convert again, should stay the same
        newcfg2 = cc_apt_configure.convert_to_v3_apt_format(newcfg)
        assert newcfg2["apt"]["sources"] == checkcfg

        # should work without raising an exception
        cc_apt_configure.convert_to_v3_apt_format({})

        with pytest.raises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format({"apt_sources": 5})

    def test_convert_to_new_format_collision(self):
        """Test the conversion of old to new format with collisions
        That matches e.g. the MAAS case specifying old and new config"""
        cfg_1_and_3 = {
            "apt": {"proxy": "http://192.168.122.1:8000/"},
            "apt_proxy": "http://192.168.122.1:8000/",
        }
        cfg_3_only = {"apt": {"proxy": "http://192.168.122.1:8000/"}}
        cfgconflict = {
            "apt": {"proxy": "http://192.168.122.1:8000/"},
            "apt_proxy": "ftp://192.168.122.1:8000/",
        }

        # collision (equal)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3)
        assert newcfg == cfg_3_only
        # collision (equal, so ok to remove)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_3_only)
        assert newcfg == cfg_3_only
        # collision (unequal)
        match = "Old and New.*unequal.*apt_proxy"
        with pytest.raises(ValueError, match=match):
            cc_apt_configure.convert_to_v3_apt_format(cfgconflict)

    def test_convert_to_new_format_dict_collision(self, apt_lists, m_gpg):
        cfg1 = {
            "source": "deb $MIRROR $RELEASE multiverse",
            "filename": apt_lists[0],
        }
        cfg2 = {
            "source": "deb $MIRROR $RELEASE main",
            "filename": apt_lists[1],
        }
        cfg3 = {
            "source": "deb $MIRROR $RELEASE universe",
            "filename": apt_lists[2],
        }
        fullv3 = {
            apt_lists[0]: {
                "filename": apt_lists[0],
                "source": "deb $MIRROR $RELEASE multiverse",
            },
            apt_lists[1]: {
                "filename": apt_lists[1],
                "source": "deb $MIRROR $RELEASE main",
            },
            apt_lists[2]: {
                "filename": apt_lists[2],
                "source": "deb $MIRROR $RELEASE universe",
            },
        }
        cfg_3_only = {"apt": {"sources": fullv3}}
        cfg_1_and_3 = {"apt_sources": [cfg1, cfg2, cfg3]}
        cfg_1_and_3.update(cfg_3_only)

        # collision (equal, so ok to remove)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3)
        assert newcfg == cfg_3_only
        # no old spec (same result)
        newcfg = cc_apt_configure.convert_to_v3_apt_format(cfg_3_only)
        assert newcfg == cfg_3_only

        diff = {
            apt_lists[0]: {
                "filename": apt_lists[0],
                "source": "deb $MIRROR $RELEASE DIFFERENTVERSE",
            },
            apt_lists[1]: {
                "filename": apt_lists[1],
                "source": "deb $MIRROR $RELEASE main",
            },
            apt_lists[2]: {
                "filename": apt_lists[2],
                "source": "deb $MIRROR $RELEASE universe",
            },
        }
        cfg_3_only = {"apt": {"sources": diff}}
        cfg_1_and_3_different = {"apt_sources": [cfg1, cfg2, cfg3]}
        cfg_1_and_3_different.update(cfg_3_only)

        # collision (unequal by dict having a different entry)
        with pytest.raises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3_different)

        missing = {
            apt_lists[0]: {
                "filename": apt_lists[0],
                "source": "deb $MIRROR $RELEASE multiverse",
            }
        }
        cfg_3_only = {"apt": {"sources": missing}}
        cfg_1_and_3_missing = {"apt_sources": [cfg1, cfg2, cfg3]}
        cfg_1_and_3_missing.update(cfg_3_only)
        # collision (unequal by dict missing an entry)
        with pytest.raises(ValueError):
            cc_apt_configure.convert_to_v3_apt_format(cfg_1_and_3_missing)
