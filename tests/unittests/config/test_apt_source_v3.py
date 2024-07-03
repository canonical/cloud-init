# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

"""test_handler_apt_source_v3
Testing various config variations of the apt_source custom config
This tries to call all in the new v3 format and cares about new features
"""
import logging
import os
import pathlib
import re
import socket
from unittest import mock
from unittest.mock import call

import pytest

from cloudinit import gpg, subp, util
from cloudinit.config import cc_apt_configure
from tests.unittests.helpers import skipIfAptPkg
from tests.unittests.util import get_cloud

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

MOCK_LSB_RELEASE_DATA = {
    "id": "Ubuntu",
    "description": "Ubuntu 18.04.1 LTS",
    "release": "18.04",
    "codename": "bionic",
}

M_PATH = "cloudinit.config.cc_apt_configure."


class TestAptSourceConfig:
    """TestAptSourceConfig
    Main Class to test apt configs
    """

    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmpdir):
        mocker.patch(
            f"{M_PATH}util.lsb_release",
            return_value=MOCK_LSB_RELEASE_DATA.copy(),
        )
        mocker.patch(f"{M_PATH}_ensure_dependencies")
        self.aptlistfile = tmpdir.join("src1.list").strpath
        self.aptlistfile2 = tmpdir.join("src2.list").strpath
        self.aptlistfile3 = tmpdir.join("src3.list").strpath
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search

    @staticmethod
    def _add_apt_sources(cfg, cloud, gpg, **kwargs):
        # with mock.patch.object(cloud.distro, "update_package_sources"):
        cc_apt_configure.add_apt_sources(cfg, cloud, gpg, **kwargs)

    @staticmethod
    def _get_default_params():
        """get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params["RELEASE"] = MOCK_LSB_RELEASE_DATA["release"]
        arch = "amd64"
        params["MIRROR"] = cc_apt_configure.get_default_mirrors(arch)[
            "PRIMARY"
        ]
        return params

    def _apt_src_basic(self, filename, cfg, tmpdir, gpg):
        """_apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        self._add_apt_sources(
            cfg,
            cloud=mock.Mock(),
            gpg=gpg,
            template_params=params,
            aa_repo_match=self.matcher,
        )

        assert (
            os.path.isfile(filename) is True
        ), f"Missing expected file {filename}"

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://test.ubuntu.com/ubuntu",
                "karmic-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        ), f"Unexpected APT config in {filename}: {contents}"

    def test_apt_v3_src_basic(self, tmpdir, m_gpg):
        """test_apt_v3_src_basic - Test fix deb source string"""
        cfg = {
            self.aptlistfile: {
                "source": (
                    "deb http://test.ubuntu.com/ubuntu"
                    " karmic-backports"
                    " main universe multiverse restricted"
                )
            }
        }
        self._apt_src_basic(self.aptlistfile, cfg, tmpdir, m_gpg)

    def test_apt_v3_src_basic_tri(self, tmpdir, m_gpg):
        """test_apt_v3_src_basic_tri - Test multiple fix deb source strings"""
        cfg = {
            self.aptlistfile: {
                "source": (
                    "deb http://test.ubuntu.com/ubuntu"
                    " karmic-backports"
                    " main universe multiverse restricted"
                )
            },
            self.aptlistfile2: {
                "source": (
                    "deb http://test.ubuntu.com/ubuntu"
                    " precise-backports"
                    " main universe multiverse restricted"
                )
            },
            self.aptlistfile3: {
                "source": (
                    "deb http://test.ubuntu.com/ubuntu"
                    " lucid-backports"
                    " main universe multiverse restricted"
                )
            },
        }
        self._apt_src_basic(self.aptlistfile, cfg, tmpdir, m_gpg)

        # extra verify on two extra files of this test
        contents = util.load_text_file(self.aptlistfile2)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://test.ubuntu.com/ubuntu",
                "precise-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        ), f"Unexpected APT format of {self.aptlistfile2}: contents"
        contents = util.load_text_file(self.aptlistfile3)
        assert re.search(
            r"%s %s %s %s\n"
            % (
                "deb",
                "http://test.ubuntu.com/ubuntu",
                "lucid-backports",
                "main universe multiverse restricted",
            ),
            contents,
            flags=re.IGNORECASE,
        ), f"Unexpected APT format of {self.aptlistfile3}: contents"

    def _apt_src_replacement(self, filename, cfg, tmpdir, gpg):
        """apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        self._add_apt_sources(
            cfg,
            cloud=mock.Mock(),
            gpg=gpg,
            template_params=params,
            aa_repo_match=self.matcher,
        )

        assert os.path.isfile(filename) is True, f"Unexpected file {filename}"

        contents = util.load_text_file(filename)
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "multiverse"),
            contents,
            flags=re.IGNORECASE,
        )

    def test_apt_v3_src_replace(self, tmpdir, m_gpg):
        """test_apt_v3_src_replace - Test replacement of MIRROR & RELEASE"""
        cfg = {self.aptlistfile: {"source": "deb $MIRROR $RELEASE multiverse"}}
        self._apt_src_replacement(self.aptlistfile, cfg, tmpdir, m_gpg)

    def test_apt_v3_src_replace_fn(self, tmpdir, m_gpg):
        """test_apt_v3_src_replace_fn - Test filename overwritten in dict"""
        cfg = {
            "ignored": {
                "source": "deb $MIRROR $RELEASE multiverse",
                "filename": self.aptlistfile,
            }
        }
        # second file should overwrite the dict key
        self._apt_src_replacement(self.aptlistfile, cfg, tmpdir, m_gpg)

    def _apt_src_replace_tri(self, cfg, tmpdir, gpg):
        """_apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self._apt_src_replacement(self.aptlistfile, cfg, tmpdir, gpg)

        # extra verify on two extra files of this test
        params = self._get_default_params()
        contents = util.load_text_file(self.aptlistfile2)
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "main"),
            contents,
            flags=re.IGNORECASE,
        ), f"Unexpected APT format {self.aptlistfile2}: {contents}"
        contents = util.load_text_file(self.aptlistfile3)
        assert re.search(
            r"%s %s %s %s\n"
            % ("deb", params["MIRROR"], params["RELEASE"], "universe"),
            contents,
            flags=re.IGNORECASE,
        ), f"Unexpected APT format {self.aptlistfile3}: {contents}"

    def test_apt_v3_src_replace_tri(self, tmpdir, m_gpg):
        """test_apt_v3_src_replace_tri - Test multiple replace/overwrites"""
        cfg = {
            self.aptlistfile: {"source": "deb $MIRROR $RELEASE multiverse"},
            "notused": {
                "source": "deb $MIRROR $RELEASE main",
                "filename": self.aptlistfile2,
            },
            self.aptlistfile3: {"source": "deb $MIRROR $RELEASE universe"},
        }
        self._apt_src_replace_tri(cfg, tmpdir, m_gpg)

    def _apt_src_keyid(
        self, filename, cfg, keynum, tmpdir, gpg, is_hardened=None
    ):
        """_apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        cloud = get_cloud()
        with mock.patch.object(cc_apt_configure, "add_apt_key") as mockobj:
            self._add_apt_sources(
                cfg,
                cloud=cloud,
                gpg=gpg,
                template_params=params,
                aa_repo_match=self.matcher,
            )

        # check if it added the right number of keys
        calls = []
        for key in cfg:
            if is_hardened is not None:
                calls.append(call(cfg[key], cloud, gpg, hardened=is_hardened))
            else:
                calls.append(call(cfg[key], cloud, gpg))

        mockobj.assert_has_calls(calls, any_order=True)

        assert os.path.isfile(filename) is True

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

    def test_apt_v3_src_keyid(self, tmpdir, m_gpg):
        """test_apt_v3_src_keyid - Test source + keyid with filename"""
        cfg = {
            self.aptlistfile: {
                "source": (
                    "deb "
                    "http://ppa.launchpad.net/"
                    "smoser/cloud-init-test/ubuntu"
                    " xenial main"
                ),
                "filename": self.aptlistfile,
                "keyid": "03683F77",
            }
        }
        self._apt_src_keyid(self.aptlistfile, cfg, 1, tmpdir, m_gpg)

    def test_apt_v3_src_keyid_tri(self, tmpdir, m_gpg):
        """test_apt_v3_src_keyid_tri - Test multiple src+key+file writes"""
        cfg = {
            self.aptlistfile: {
                "source": (
                    "deb "
                    "http://ppa.launchpad.net/"
                    "smoser/cloud-init-test/ubuntu"
                    " xenial main"
                ),
                "keyid": "03683F77",
            },
            "ignored": {
                "source": (
                    "deb "
                    "http://ppa.launchpad.net/"
                    "smoser/cloud-init-test/ubuntu"
                    " xenial universe"
                ),
                "keyid": "03683F77",
                "filename": self.aptlistfile2,
            },
            self.aptlistfile3: {
                "source": (
                    "deb "
                    "http://ppa.launchpad.net/"
                    "smoser/cloud-init-test/ubuntu"
                    " xenial multiverse"
                ),
                "filename": self.aptlistfile3,
                "keyid": "03683F77",
            },
        }

        self._apt_src_keyid(self.aptlistfile, cfg, 3, tmpdir, m_gpg)
        contents = util.load_text_file(self.aptlistfile2)
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
        contents = util.load_text_file(self.aptlistfile3)
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

    def test_apt_v3_src_key(self, mocker, m_gpg):
        """test_apt_v3_src_key - Test source + key"""
        params = self._get_default_params()
        cfg = {
            self.aptlistfile: {
                "source": (
                    "deb "
                    "http://ppa.launchpad.net/"
                    "smoser/cloud-init-test/ubuntu"
                    " xenial main"
                ),
                "filename": self.aptlistfile,
                "key": "fakekey 4321",
            }
        }
        mockobj = mocker.patch.object(cc_apt_configure, "apt_key")
        self._add_apt_sources(
            cfg,
            cloud=mock.Mock(),
            gpg=m_gpg,
            template_params=params,
            aa_repo_match=self.matcher,
        )

        calls = (
            call(
                "add",
                m_gpg,
                output_file=pathlib.Path(self.aptlistfile).stem,
                data="fakekey 4321",
                hardened=False,
            ),
        )
        mockobj.assert_has_calls(calls, any_order=True)
        contents = util.load_text_file(self.aptlistfile)
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

    def test_apt_v3_src_keyonly(self, mocker, m_gpg):
        """test_apt_v3_src_keyonly - Test key without source"""
        m_gpg.getkeybyid = mock.Mock(return_value="fakekey 4242")
        params = self._get_default_params()
        cfg = {self.aptlistfile: {"key": "fakekey 4242"}}

        mockobj = mocker.patch.object(cc_apt_configure, "apt_key")
        self._add_apt_sources(
            cfg,
            cloud=mock.Mock(),
            gpg=m_gpg,
            template_params=params,
            aa_repo_match=self.matcher,
        )

        calls = (
            call(
                "add",
                m_gpg,
                output_file=pathlib.Path(self.aptlistfile).stem,
                data="fakekey 4242",
                hardened=False,
            ),
        )
        mockobj.assert_has_calls(calls, any_order=True)

        # filename should be ignored on key only
        assert os.path.isfile(self.aptlistfile) is False

    def test_apt_v3_src_keyidonly(self, m_gpg):
        """test_apt_v3_src_keyidonly - Test keyid without source"""
        m_gpg.getkeybyid = mock.Mock(return_value="fakekey 1212")
        params = self._get_default_params()
        cfg = {self.aptlistfile: {"keyid": "03683F77"}}
        with mock.patch.object(
            subp, "subp", return_value=("fakekey 1212", "")
        ):
            with mock.patch.object(cc_apt_configure, "apt_key") as mockobj:
                self._add_apt_sources(
                    cfg,
                    cloud=mock.Mock(),
                    gpg=m_gpg,
                    template_params=params,
                    aa_repo_match=self.matcher,
                )

        calls = (
            call(
                "add",
                m_gpg,
                output_file=pathlib.Path(self.aptlistfile).stem,
                data="fakekey 1212",
                hardened=False,
            ),
        )
        mockobj.assert_has_calls(calls, any_order=True)

        # filename should be ignored on key only
        assert (
            os.path.isfile(self.aptlistfile) is False
        ), f"Unexpected file {self.aptlistfile} found"

    def apt_src_keyid_real(self, cfg, expectedkey, gpg, is_hardened=None):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        params = self._get_default_params()

        with mock.patch.object(cc_apt_configure, "add_apt_key_raw") as mockkey:
            with mock.patch.object(
                gpg, "getkeybyid", return_value=expectedkey
            ) as mockgetkey:
                self._add_apt_sources(
                    cfg,
                    cloud=mock.Mock(),
                    gpg=gpg,
                    template_params=params,
                    aa_repo_match=self.matcher,
                )

        keycfg = cfg[self.aptlistfile]
        mockgetkey.assert_called_with(
            keycfg["keyid"], keycfg.get("keyserver", "keyserver.ubuntu.com")
        )
        if is_hardened is not None:
            mockkey.assert_called_with(
                expectedkey,
                keycfg["keyfile"],
                gpg,
                hardened=is_hardened,
            )

        # filename should be ignored on key only
        assert os.path.isfile(self.aptlistfile) is False

    def test_apt_v3_src_keyid_real(self, m_gpg):
        """test_apt_v3_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {self.aptlistfile: {"keyid": keyid, "keyfile": self.aptlistfile}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY, m_gpg, is_hardened=False)

    def test_apt_v3_src_longkeyid_real(self, m_gpg):
        """test_apt_v3_src_longkeyid_real Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {"keyid": keyid, "keyfile": self.aptlistfile}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY, m_gpg, is_hardened=False)

    def test_apt_v3_src_longkeyid_ks_real(self, m_gpg):
        """test_apt_v3_src_longkeyid_ks_real Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {
            self.aptlistfile: {
                "keyid": keyid,
                "keyfile": self.aptlistfile,
                "keyserver": "keys.gnupg.net",
            }
        }

        self.apt_src_keyid_real(cfg, EXPECTEDKEY, m_gpg)

    def test_apt_v3_src_keyid_keyserver(self, m_gpg):
        """test_apt_v3_src_keyid_keyserver - Test custom keyserver"""
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {
            self.aptlistfile: {
                "keyid": keyid,
                "keyfile": self.aptlistfile,
                "keyserver": "test.random.com",
            }
        }

        # in some test environments only *.ubuntu.com is reachable
        # so mock the call and check if the config got there
        with mock.patch.object(cc_apt_configure, "add_apt_key_raw") as mockadd:
            self._add_apt_sources(
                cfg,
                cloud=mock.Mock(),
                gpg=m_gpg,
                template_params=params,
                aa_repo_match=self.matcher,
            )

        m_gpg.getkeybyid.assert_called_with("03683F77", "test.random.com")
        mockadd.assert_called_with(
            "<mocked: getkeybyid>",
            self.aptlistfile,
            m_gpg,
            hardened=False,
        )

        # filename should be ignored on key only
        assert os.path.isfile(self.aptlistfile) is False

    def test_apt_v3_src_ppa(self, m_gpg):
        """test_apt_v3_src_ppa - Test specification of a ppa"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {"source": "ppa:smoser/cloud-init-test"}}

        with mock.patch("cloudinit.subp.subp") as mockobj:
            self._add_apt_sources(
                cfg,
                cloud=mock.Mock(),
                gpg=m_gpg,
                template_params=params,
                aa_repo_match=self.matcher,
            )
        mockobj.assert_any_call(
            [
                "add-apt-repository",
                "--no-update",
                "ppa:smoser/cloud-init-test",
            ],
        )

        # adding ppa should ignore filename (uses add-apt-repository)
        assert (
            os.path.isfile(self.aptlistfile) is False
        ), f"Unexpected file found {self.aptlistfile}"

    def test_apt_v3_src_ppa_tri(self, m_gpg):
        """test_apt_v3_src_ppa_tri - Test specification of multiple ppa's"""
        params = self._get_default_params()
        cfg = {
            self.aptlistfile: {"source": "ppa:smoser/cloud-init-test"},
            self.aptlistfile2: {"source": "ppa:smoser/cloud-init-test2"},
            self.aptlistfile3: {"source": "ppa:smoser/cloud-init-test3"},
        }

        with mock.patch("cloudinit.subp.subp") as mockobj:
            self._add_apt_sources(
                cfg,
                cloud=mock.Mock(),
                gpg=m_gpg,
                template_params=params,
                aa_repo_match=self.matcher,
            )
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
        for path in [self.aptlistfile, self.aptlistfile2, self.aptlistfile3]:
            assert not os.path.isfile(
                self.aptlistfile
            ), f"Unexpected file {path}"

    @mock.patch("cloudinit.config.cc_apt_configure.util.get_dpkg_architecture")
    def test_apt_v3_list_rename(self, m_get_dpkg_architecture):
        """test_apt_v3_list_rename - Test find mirror and apt list renaming"""
        pre = cc_apt_configure.APT_LISTS
        # filenames are archive dependent

        arch = "s390x"
        m_get_dpkg_architecture.return_value = arch
        component = "ubuntu-ports"
        archive = "ports.ubuntu.com"

        cfg = {
            "primary": [
                {
                    "arches": ["default"],
                    "uri": "http://test.ubuntu.com/%s/" % component,
                }
            ],
            "security": [
                {
                    "arches": ["default"],
                    "uri": "http://testsec.ubuntu.com/%s/" % component,
                }
            ],
        }
        post = "%s_dists_%s-updates_InRelease" % (
            component,
            MOCK_LSB_RELEASE_DATA["codename"],
        )
        fromfn = "%s/%s_%s" % (pre, archive, post)
        tofn = "%s/test.ubuntu.com_%s" % (pre, post)

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, get_cloud(), arch)

        assert mirrors["MIRROR"] == "http://test.ubuntu.com/%s/" % component
        assert mirrors["PRIMARY"] == "http://test.ubuntu.com/%s/" % component
        assert (
            mirrors["SECURITY"] == "http://testsec.ubuntu.com/%s/" % component
        )

        with mock.patch.object(cc_apt_configure.os, "rename") as mockren:
            with mock.patch.object(
                cc_apt_configure.glob, "glob", return_value=[fromfn]
            ):
                cc_apt_configure.rename_apt_lists(mirrors, arch)

        mockren.assert_any_call(fromfn, tofn)

    @staticmethod
    def test_apt_v3_proxy():
        """test_apt_v3_proxy - Test apt_*proxy configuration"""
        cfg = {
            "proxy": "foobar1",
            "http_proxy": "foobar2",
            "ftp_proxy": "foobar3",
            "https_proxy": "foobar4",
        }

        with mock.patch.object(util, "write_file") as mockobj:
            cc_apt_configure.apply_apt_config(cfg, "proxyfn", "notused")

        mockobj.assert_called_with(
            "proxyfn",
            'Acquire::http::Proxy "foobar1";\n'
            'Acquire::http::Proxy "foobar2";\n'
            'Acquire::ftp::Proxy "foobar3";\n'
            'Acquire::https::Proxy "foobar4";\n',
        )

    def test_apt_v3_mirror(self):
        """test_apt_v3_mirror - Test defining a mirror"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {
            "primary": [{"arches": ["default"], "uri": pmir}],
            "security": [{"arches": ["default"], "uri": smir}],
        }

        mirrors = cc_apt_configure.find_apt_mirror_info(
            cfg, get_cloud(), "amd64"
        )

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_mirror_default(self):
        """test_apt_v3_mirror_default - Test without defining a mirror"""
        arch = "amd64"
        default_mirrors = cc_apt_configure.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mycloud = get_cloud()
        mirrors = cc_apt_configure.find_apt_mirror_info({}, mycloud, arch)

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_mirror_arches(self):
        """test_apt_v3_mirror_arches - Test arches selection of mirror"""
        pmir = "http://my-primary.ubuntu.com/ubuntu/"
        smir = "http://my-security.ubuntu.com/ubuntu/"
        arch = "ppc64el"
        cfg = {
            "primary": [
                {"arches": ["default"], "uri": "notthis-primary"},
                {"arches": [arch], "uri": pmir},
            ],
            "security": [
                {"arches": ["default"], "uri": "nothis-security"},
                {"arches": [arch], "uri": smir},
            ],
        }

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, get_cloud(), arch)

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_mirror_arches_default(self):
        """test_apt_v3_mirror_arches - Test falling back to default arch"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {
            "primary": [
                {"arches": ["default"], "uri": pmir},
                {"arches": ["thisarchdoesntexist"], "uri": "notthis"},
            ],
            "security": [
                {"arches": ["thisarchdoesntexist"], "uri": "nothat"},
                {"arches": ["default"], "uri": smir},
            ],
        }

        mirrors = cc_apt_configure.find_apt_mirror_info(
            cfg, get_cloud(), "amd64"
        )

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    @mock.patch("cloudinit.config.cc_apt_configure.util.get_dpkg_architecture")
    def test_apt_v3_get_def_mir_non_intel_no_arch(
        self, m_get_dpkg_architecture
    ):
        arch = "ppc64el"
        m_get_dpkg_architecture.return_value = arch
        expected = {
            "PRIMARY": "http://ports.ubuntu.com/ubuntu-ports",
            "SECURITY": "http://ports.ubuntu.com/ubuntu-ports",
        }
        assert expected == cc_apt_configure.get_default_mirrors()

    def test_apt_v3_get_default_mirrors_non_intel_with_arch(self):
        expected = {
            "PRIMARY": "http://ports.ubuntu.com/ubuntu-ports",
            "SECURITY": "http://ports.ubuntu.com/ubuntu-ports",
        }
        assert expected == cc_apt_configure.get_default_mirrors("ppc64el")

    def test_apt_v3_mirror_arches_sysdefault(self):
        """test_apt_v3_mirror_arches - Test arches fallback to sys default"""
        arch = "amd64"
        default_mirrors = cc_apt_configure.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mycloud = get_cloud()
        cfg = {
            "primary": [
                {"arches": ["thisarchdoesntexist_64"], "uri": "notthis"},
                {"arches": ["thisarchdoesntexist"], "uri": "notthiseither"},
            ],
            "security": [
                {"arches": ["thisarchdoesntexist"], "uri": "nothat"},
                {"arches": ["thisarchdoesntexist_64"], "uri": "nothateither"},
            ],
        }

        mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_mirror_search(self):
        """test_apt_v3_mirror_search - Test searching mirrors in a list
        mock checks to avoid relying on network connectivity"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {
            "primary": [{"arches": ["default"], "search": ["pfailme", pmir]}],
            "security": [{"arches": ["default"], "search": ["sfailme", smir]}],
        }

        with mock.patch.object(
            cc_apt_configure.util,
            "search_for_mirror",
            side_effect=[pmir, smir],
        ) as mocksearch:
            mirrors = cc_apt_configure.find_apt_mirror_info(
                cfg, get_cloud(), "amd64"
            )

        calls = [call(["pfailme", pmir]), call(["sfailme", smir])]
        mocksearch.assert_has_calls(calls)

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_mirror_search_many2(self):
        """test_apt_v3_mirror_search_many3 - Test both mirrors specs at once"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {
            "primary": [
                {
                    "arches": ["default"],
                    "uri": pmir,
                    "search": ["pfailme", "foo"],
                }
            ],
            "security": [
                {
                    "arches": ["default"],
                    "uri": smir,
                    "search": ["sfailme", "bar"],
                }
            ],
        }

        arch = "amd64"

        # should be called only once per type, despite two mirror configs
        mycloud = None
        with mock.patch.object(
            cc_apt_configure, "get_mirror", return_value="http://mocked/foo"
        ) as mockgm:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [
            call(cfg, "primary", arch, mycloud),
            call(cfg, "security", arch, mycloud),
        ]
        mockgm.assert_has_calls(calls)

        # should not be called, since primary is specified
        with mock.patch.object(
            cc_apt_configure.util, "search_for_mirror"
        ) as mockse:
            mirrors = cc_apt_configure.find_apt_mirror_info(
                cfg, get_cloud(), arch
            )
        mockse.assert_not_called()

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    @pytest.mark.allow_dns_lookup
    def test_apt_v3_url_resolvable(self):
        """test_apt_v3_url_resolvable - Test resolving urls"""

        with mock.patch.object(util, "is_resolvable") as mockresolve:
            util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mockresolve.assert_called_with("http://1.2.3.4/ubuntu")

        with mock.patch.object(util, "is_resolvable") as mockresolve:
            util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
        mockresolve.assert_called_with("http://us.archive.ubuntu.com/ubuntu")

        # former tests can leave this set (or not if the test is ran directly)
        # do a hard reset to ensure a stable result
        util._DNS_REDIRECT_IP = None
        bad = [(None, None, None, "badname", ["10.3.2.1"])]
        good = [(None, None, None, "goodname", ["10.2.3.4"])]
        with mock.patch.object(
            socket, "getaddrinfo", side_effect=[bad, bad, bad, good, good]
        ) as mocksock:
            ret = util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
            ret2 = util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mocksock.assert_any_call(
            "does-not-exist.example.com.", None, 0, 0, 1, 2
        )
        mocksock.assert_any_call("example.invalid.", None, 0, 0, 1, 2)
        mocksock.assert_any_call("us.archive.ubuntu.com", None)

        assert ret is True
        assert ret2 is True

        # side effect need only bad ret after initial call
        with mock.patch.object(
            socket, "getaddrinfo", side_effect=[bad]
        ) as mocksock:
            ret3 = util.is_resolvable_url("http://failme.com/ubuntu")
        calls = [call("failme.com", None)]
        mocksock.assert_has_calls(calls)
        assert ret3 is False

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
        assert expect == result

        # single disable release suite
        disabled = ["$RELEASE"]
        expect = """\
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

        # single disable other suite
        disabled = ["$RELEASE-updates"]
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu"""
            """ xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

        # multi disable
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

        # multi line disable (same suite multiple times in input)
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
# suite disabled by cloud-init: deb http://UBUNTU.com//ubuntu """
            """xenial-updates main
# suite disabled by cloud-init: deb http://UBUNTU.COM//ubuntu """
            """xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

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
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
#deb http://UBUNTU.com//ubuntu xenial-updates main
# suite disabled by cloud-init: deb http://UBUNTU.COM//ubuntu """
            """xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

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
        assert expect == result

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
        assert expect == result

        # single disable suite with option
        disabled = ["$RELEASE-updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
# suite disabled by cloud-init: deb [a=b] http://ubu.com//ubu """
            """xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

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
        assert expect == result

        # single disable suite while options at others
        disabled = ["$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = (
            """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
# suite disabled by cloud-init: deb http://ubuntu.com//ubuntu """
            """xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        )
        result = cc_apt_configure.disable_suites(disabled, orig, release)
        assert expect == result

    def test_disable_suites_blank_lines(self):
        """test_disable_suites_blank_lines - ensure blank lines allowed"""
        lines = [
            "deb %(repo)s %(rel)s main universe",
            "",
            "deb %(repo)s %(rel)s-updates main universe",
            "   # random comment",
            "#comment here",
            "",
        ]
        rel = "trusty"
        repo = "http://example.com/mirrors/ubuntu"
        orig = "\n".join(lines) % {"repo": repo, "rel": rel}

        assert orig == cc_apt_configure.disable_suites(["proposed"], orig, rel)

    @mock.patch("cloudinit.util.get_hostname", return_value="abc.localdomain")
    def test_apt_v3_mirror_search_dns(self, m_get_hostname):
        """test_apt_v3_mirror_search_dns - Test searching dns patterns"""
        pmir = "phit"
        smir = "shit"
        arch = "amd64"
        mycloud = get_cloud("ubuntu")
        cfg = {
            "primary": [{"arches": ["default"], "search_dns": True}],
            "security": [{"arches": ["default"], "search_dns": True}],
        }

        with mock.patch.object(
            cc_apt_configure, "get_mirror", return_value="http://mocked/foo"
        ) as mockgm:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [
            call(cfg, "primary", arch, mycloud),
            call(cfg, "security", arch, mycloud),
        ]
        mockgm.assert_has_calls(calls)

        with mock.patch.object(
            cc_apt_configure,
            "search_for_mirror_dns",
            return_value="http://mocked/foo",
        ) as mocksdns:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)
        calls = [
            call(True, "primary", cfg, mycloud),
            call(True, "security", cfg, mycloud),
        ]
        mocksdns.assert_has_calls(calls)

        # first return is for the non-dns call before
        with mock.patch.object(
            cc_apt_configure.util,
            "search_for_mirror",
            side_effect=[None, pmir, None, smir],
        ) as mockse:
            mirrors = cc_apt_configure.find_apt_mirror_info(cfg, mycloud, arch)

        calls = [
            call(None),
            call(
                [
                    "http://ubuntu-mirror.localdomain/ubuntu",
                    "http://ubuntu-mirror/ubuntu",
                ]
            ),
            call(None),
            call(
                [
                    "http://ubuntu-security-mirror.localdomain/ubuntu",
                    "http://ubuntu-security-mirror/ubuntu",
                ]
            ),
        ]
        mockse.assert_has_calls(calls)

        assert mirrors["MIRROR"] == pmir
        assert mirrors["PRIMARY"] == pmir
        assert mirrors["SECURITY"] == smir

    def test_apt_v3_add_mirror_keys(self, tmpdir, m_gpg):
        """test_apt_v3_add_mirror_keys - Test adding key for mirrors"""
        arch = "amd64"
        cfg = {
            "primary": [
                {
                    "arches": [arch],
                    "uri": "http://test.ubuntu.com/",
                    "filename": "primary",
                    "key": "fakekey_primary",
                }
            ],
            "security": [
                {
                    "arches": [arch],
                    "uri": "http://testsec.ubuntu.com/",
                    "filename": "security",
                    "key": "fakekey_security",
                }
            ],
        }

        with mock.patch.object(cc_apt_configure, "add_apt_key_raw") as mockadd:
            cc_apt_configure.add_mirror_keys(cfg, None, gpg)
        calls = [
            mock.call("fakekey_primary", "primary", gpg, hardened=False),
            mock.call("fakekey_security", "security", gpg, hardened=False),
        ]
        mockadd.assert_has_calls(calls, any_order=True)


class TestDebconfSelections:
    @mock.patch("cloudinit.config.cc_apt_configure.subp.subp")
    def test_set_sel_appends_newline_if_absent(self, m_subp):
        """Automatically append a newline to debconf-set-selections config."""
        selections = b"some/setting boolean true"
        cc_apt_configure.debconf_set_selections(selections=selections)
        cc_apt_configure.debconf_set_selections(selections=selections + b"\n")
        m_call = mock.call(
            ["debconf-set-selections"],
            data=selections + b"\n",
            capture=True,
        )
        assert [m_call, m_call] == m_subp.call_args_list

    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    def test_no_set_sel_if_none_to_set(self, m_set_sel):
        cc_apt_configure.apply_debconf_selections({"foo": "bar"})
        m_set_sel.assert_not_called()

    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    @mock.patch(
        "cloudinit.config.cc_apt_configure.util.get_installed_packages"
    )
    def test_set_sel_call_has_expected_input(self, m_get_inst, m_set_sel):
        data = {
            "set1": "pkga pkga/q1 mybool false",
            "set2": (
                "pkgb\tpkgb/b1\tstr\tthis is a string\n"
                "pkgc\tpkgc/ip\tstring\t10.0.0.1"
            ),
        }
        lines = "\n".join(data.values()).split("\n")

        m_get_inst.return_value = ["adduser", "apparmor"]
        m_set_sel.return_value = None

        cc_apt_configure.apply_debconf_selections({"debconf_selections": data})
        assert m_get_inst.called is True
        assert m_set_sel.call_count == 1

        # assumes called with *args value.
        selections = m_set_sel.call_args_list[0][0][0].decode()

        missing = [
            line for line in lines if line not in selections.splitlines()
        ]
        assert [] == missing

    @mock.patch("cloudinit.config.cc_apt_configure.dpkg_reconfigure")
    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    @mock.patch(
        "cloudinit.config.cc_apt_configure.util.get_installed_packages"
    )
    def test_reconfigure_if_intersection(
        self, m_get_inst, m_set_sel, m_dpkg_r
    ):
        data = {
            "set1": "pkga pkga/q1 mybool false",
            "set2": (
                "pkgb\tpkgb/b1\tstr\tthis is a string\n"
                "pkgc\tpkgc/ip\tstring\t10.0.0.1"
            ),
            "cloud-init": "cloud-init cloud-init/datasourcesmultiselect MAAS",
        }

        m_set_sel.return_value = None
        m_get_inst.return_value = [
            "adduser",
            "apparmor",
            "pkgb",
            "cloud-init",
            "zdog",
        ]

        cc_apt_configure.apply_debconf_selections({"debconf_selections": data})

        # reconfigure should be called with the intersection
        # of (packages in config, packages installed)
        assert m_dpkg_r.call_count == 1
        # assumes called with *args (dpkg_reconfigure([a,b,c], target=))
        packages = m_dpkg_r.call_args_list[0][0][0]
        assert set(["cloud-init", "pkgb"]) == set(packages)

    @mock.patch("cloudinit.config.cc_apt_configure.dpkg_reconfigure")
    @mock.patch("cloudinit.config.cc_apt_configure.debconf_set_selections")
    @mock.patch(
        "cloudinit.config.cc_apt_configure.util.get_installed_packages"
    )
    def test_reconfigure_if_no_intersection(
        self, m_get_inst, m_set_sel, m_dpkg_r
    ):
        data = {"set1": "pkga pkga/q1 mybool false"}

        m_get_inst.return_value = [
            "adduser",
            "apparmor",
            "pkgb",
            "cloud-init",
            "zdog",
        ]
        m_set_sel.return_value = None

        cc_apt_configure.apply_debconf_selections({"debconf_selections": data})

        assert m_get_inst.called is True
        assert m_dpkg_r.call_count == 0

    @mock.patch("cloudinit.config.cc_apt_configure.subp.subp")
    def test_dpkg_reconfigure_does_reconfigure(self, m_subp, tmpdir):

        # due to the way the cleaners are called (via dictionary reference)
        # mocking clean_cloud_init directly does not work.  So we mock
        # the CONFIG_CLEANERS dictionary and assert our cleaner is called.
        ci_cleaner = mock.MagicMock()
        with mock.patch.dict(
            "cloudinit.config.cc_apt_configure.CONFIG_CLEANERS",
            values={"cloud-init": ci_cleaner},
            clear=True,
        ):
            cc_apt_configure.dpkg_reconfigure(["pkga", "cloud-init"])
        # cloud-init is actually the only package we have a cleaner for
        # so for now, its the only one that should reconfigured
        assert m_subp.call_count == 1
        found = m_subp.call_args_list[0][0][0]
        expected = [
            "dpkg-reconfigure",
            "--frontend=noninteractive",
            "cloud-init",
        ]
        assert expected == found

    @mock.patch("cloudinit.config.cc_apt_configure.subp.subp")
    def test_dpkg_reconfigure_not_done_on_no_data(self, m_subp):
        cc_apt_configure.dpkg_reconfigure([])
        m_subp.assert_not_called()

    @mock.patch("cloudinit.config.cc_apt_configure.subp.subp")
    def test_dpkg_reconfigure_not_done_if_no_cleaners(self, m_subp):
        cc_apt_configure.dpkg_reconfigure(["pkgfoo", "pkgbar"])
        m_subp.assert_not_called()


DEB822_SINGLE_SUITE = """\
Types: deb
URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
Suites: mantic  # Some comment
Components: main
"""

DEB822_DISABLED_SINGLE_SUITE = """\
## Entry disabled by cloud-init, due to disable_suites
# disabled by cloud-init: Types: deb
# disabled by cloud-init: URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
# disabled by cloud-init: Suites: mantic  # Some comment
# disabled by cloud-init: Components: main
"""

DEB822_SINGLE_SECTION_TWO_SUITES = """\
Types: deb
URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
Suites: mantic mantic-updates
Components: main
"""

DEB822_SINGLE_SECTION_TWO_SUITES_DISABLE_ONE = """\
Types: deb
URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
# cloud-init disable_suites redacted: Suites: mantic mantic-updates
Suites: mantic-updates
Components: main
"""

DEB822_SUITE_2 = """
# APT Suite 2
Types: deb
URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
Suites: mantic-backports
Components: main
"""


DEB822_DISABLED_SINGLE_SUITE = """\
## Entry disabled by cloud-init, due to disable_suites
# disabled by cloud-init: Types: deb
# disabled by cloud-init: URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
# disabled by cloud-init: Suites: mantic  # Some comment
# disabled by cloud-init: Components: main
"""

DEB822_DISABLED_MULTIPLE_SUITES = """\
## Entry disabled by cloud-init, due to disable_suites
# disabled by cloud-init: Types: deb
# disabled by cloud-init: URIs: https://ppa.launchpadcontent.net/cloud-init-dev/daily/ubuntu/
# disabled by cloud-init: Suites: mantic mantic-updates
# disabled by cloud-init: Components: main
"""


class TestDisableSuitesDeb822:
    @pytest.mark.parametrize(
        "disabled_suites,src,expected",
        (
            pytest.param(
                [],
                DEB822_SINGLE_SUITE,
                DEB822_SINGLE_SUITE,
                id="empty_suites_nochange",
            ),
            pytest.param(
                ["$RELEASE-updates"],
                DEB822_SINGLE_SUITE,
                DEB822_SINGLE_SUITE,
                id="no_matching_suites_nochange",
            ),
            pytest.param(
                ["$RELEASE"],
                DEB822_SINGLE_SUITE,
                DEB822_DISABLED_SINGLE_SUITE,
                id="matching_all_suites_disables_whole_section",
            ),
            pytest.param(
                ["$RELEASE"],
                DEB822_SINGLE_SECTION_TWO_SUITES + DEB822_SUITE_2,
                DEB822_SINGLE_SECTION_TWO_SUITES_DISABLE_ONE
                + "\n"
                + DEB822_SUITE_2,
                id="matching_some_suites_redacts_matches_and_comments_orig",
            ),
            pytest.param(
                ["$RELEASE", "$RELEASE-updates"],
                DEB822_SINGLE_SECTION_TWO_SUITES + DEB822_SUITE_2,
                DEB822_DISABLED_MULTIPLE_SUITES + "\n" + DEB822_SUITE_2,
                id="matching_all_suites_disables_specific_section",
            ),
        ),
    )
    def test_disable_deb822_suites_disables_proper_suites(
        self, disabled_suites, src, expected
    ):
        assert expected == cc_apt_configure.disable_suites_deb822(
            disabled_suites, src, "mantic"
        )


APT_CONFIG_DUMP = """
APT "";
Dir "/";
Dir::Etc "etc/myapt";
Dir::Etc::sourcelist "sources.my.list";
Dir::Etc::sourceparts "sources.my.list.d";
Dir::Etc::main "apt.conf";
"""


class TestGetAptCfg:
    @skipIfAptPkg()
    @pytest.mark.parametrize(
        "subp_side_effect,expected",
        (
            pytest.param(
                [(APT_CONFIG_DUMP, "")],
                {
                    "sourcelist": "/etc/myapt/sources.my.list",
                    "sourceparts": "/etc/myapt/sources.my.list.d/",
                },
                id="no_aptpkg_use_apt_config_cmd",
            ),
            pytest.param(
                [("", "")],
                {
                    "sourcelist": "/etc/apt/sources.list",
                    "sourceparts": "/etc/apt/sources.list.d/",
                },
                id="no_aptpkg_unparsable_apt_config_cmd_defaults",
            ),
            pytest.param(
                [
                    subp.ProcessExecutionError(
                        "No such file or directory 'apt-config'"
                    )
                ],
                {
                    "sourcelist": "/etc/apt/sources.list",
                    "sourceparts": "/etc/apt/sources.list.d/",
                },
                id="no_aptpkg_no_apt_config_cmd_defaults",
            ),
        ),
    )
    def test_use_defaults_or_apt_config_dump(
        self, subp_side_effect, expected, mocker
    ):
        subp = mocker.patch("cloudinit.config.cc_apt_configure.subp.subp")
        subp.side_effect = subp_side_effect
        assert expected == cc_apt_configure.get_apt_cfg()
        subp.assert_called_once_with(["apt-config", "dump"])


class TestIsDeb822SourcesFormat:
    @pytest.mark.parametrize(
        "content,is_deb822,warnings",
        (
            pytest.param(
                "#Something\ndeb-src http://url lunar multiverse\n",
                False,
                [],
                id="any_deb_src_is_not_deb822",
            ),
            pytest.param(
                "#Something\ndeb http://url lunar multiverse\n",
                False,
                [],
                id="any_deb_url_is_not_deb822",
            ),
            pytest.param(
                "#Something\ndeb http://url lunar multiverse\nTypes: deb\n",
                False,
                [],
                id="even_some_deb822_fields_not_deb822_if_any_deb_line",
            ),
            pytest.param(
                "#Something\nTypes: deb\n",
                True,
                [],
                id="types_deb822_keys_and_no_deb_or_deb_src_is_deb822",
            ),
            pytest.param(
                "#Something\nURIs: http://url\n",
                True,
                [],
                id="uris_deb822_keys_and_no_deb_or_deb_src_is_deb822",
            ),
            pytest.param(
                "#Something\nSuites: http://url\n",
                True,
                [],
                id="suites_deb822_keys_and_no_deb_deb_src_is_deb822",
            ),
            pytest.param(
                "#Something\nComponents: http://url\n",
                True,
                [],
                id="components_deb822_keys_and_no_deb_deb_src_is_deb822",
            ),
            pytest.param(
                "#Something neither deb/deb-src nor deb822\n",
                False,
                [
                    "apt.sources_list value does not match either deb822"
                    " source keys or deb/deb-src list keys. Assuming APT"
                    " deb/deb-src list format."
                ],
                id="neither_deb822_keys_nor_deb_deb_src_warn_and_not_deb822",
            ),
        ),
    )
    def test_is_deb822_format_prefers_non_deb822(
        self, content, is_deb822, warnings, caplog
    ):
        with caplog.at_level(logging.WARNING):
            assert is_deb822 is cc_apt_configure.is_deb822_sources_format(
                content
            )
        for warning in warnings:
            assert warning in caplog.text
