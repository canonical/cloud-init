# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

"""test_handler_apt_configure_sources_list
Test templating of sources list
"""
import stat

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from cloudinit.subp import SubpResult
from tests.unittests.util import get_cloud

EXAMPLE_TMPL = """\
## template:jinja
## Note, this file is written by cloud-init on first boot of an instance
deb {{mirror}} {{codename}} main restricted
deb-src {{mirror}} {{codename}} main restricted
"""

YAML_TEXT_CUSTOM_SL = """
apt_mirror: http://archive.ubuntu.com/ubuntu/
apt_custom_sources_list: |
    ## Note, this file is written by cloud-init on first boot of an instance
    deb $MIRROR $RELEASE main restricted
    deb-src $MIRROR $RELEASE main restricted
    # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = """## Note, this file is written by cloud-init on first boot of an instance
deb http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
deb-src http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
"""  # noqa: E501

EXAMPLE_TMPL_DEB822 = """\
## template:jinja
Types: deb deb-src
URIs: {{mirror}}
Suites: {{codename}} {{codename}}-updates
Components: main restricted

# Security section
Types: deb deb-src
URIs: {{security}}
Suites: {{codename}}-security
Components: main restricted
"""

YAML_TEXT_CUSTOM_SL_DEB822 = """
apt_mirror: http://archive.ubuntu.com/ubuntu/
apt_custom_sources_list: |
    ## template:jinja
    Types: deb deb-src
    URIs: {{mirror}}
    Suites: {{codename}} {{codename}}-updates
    Components: main restricted

    # Security section
    Types: deb deb-src
    URIs: {{security}}
    Suites: {{codename}}-security
    Components: main restricted
    # custom_sources_list
"""

EXPECTED_CONVERTED_CONTENT_DEB822 = """\
Types: deb deb-src
URIs: http://archive.ubuntu.com/ubuntu/
Suites: fakerelease fakerelease-updates
Components: main restricted

# Security section
Types: deb deb-src
URIs: http://archive.ubuntu.com/ubuntu/
Suites: fakerelease-security
Components: main restricted
"""


@pytest.mark.usefixtures("fake_filesystem")
class TestAptSourceConfigSourceList:
    """TestAptSourceConfigSourceList
    Main Class to test sources list rendering
    """

    @pytest.fixture(autouse=True)
    def common_mocks(self, mocker):
        self.subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult("PPID   PID", "")
        )
        mocker.patch("cloudinit.config.cc_apt_configure._ensure_dependencies")
        lsb = mocker.patch("cloudinit.util.lsb_release")
        lsb.return_value = {"codename": "fakerelease"}
        m_arch = mocker.patch("cloudinit.util.get_dpkg_architecture")
        m_arch.return_value = "amd64"
        self.deb822 = mocker.patch.object(
            cc_apt_configure.features, "APT_DEB822_SOURCE_LIST_FILE", True
        )
        mocker.patch.object(
            cc_apt_configure,
            "get_apt_cfg",
            return_value={
                "sourcelist": "/etc/apt/sources.list",
                "sourceparts": "/etc/apt/sources.list.d/",
            },
        )

    def apt_source_list(self, distro, mirror, tmpdir, mirrorcheck=None):
        """apt_source_list
        Test rendering of a source.list from template for a given distro
        """
        if mirrorcheck is None:
            mirrorcheck = mirror

        if isinstance(mirror, list):
            cfg = {"apt_mirror_search": mirror}
            expected = EXPECTED_CONVERTED_CONTENT.replace(
                "http://archive.ubuntu.com/ubuntu/", mirror[-1]
            )
        else:
            cfg = {"apt_mirror": mirror}
            expected = EXPECTED_CONVERTED_CONTENT.replace(
                "http://archive.ubuntu.com/ubuntu/", mirror
            )

        mycloud = get_cloud(distro)
        tmpl_file = f"/etc/cloud/templates/sources.list.{distro}.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL)

        cc_apt_configure.handle("test", cfg, mycloud, None)
        sources_file = tmpdir.join("/etc/apt/sources.list")
        assert expected == sources_file.read()
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

    @pytest.mark.parametrize(
        "distro,mirror",
        (
            (
                "ubuntu",
                "http://archive.ubuntu.com/ubuntu/",
            ),
            (
                "debian",
                "http://httpredir.debian.org/debian/",
            ),
        ),
    )
    def test_apt_v1_source_list_by_distro(self, distro, mirror, tmpdir):
        """Test rendering of a source.list from template for each distro"""
        mycloud = get_cloud(distro)
        tmpl_file = f"/etc/cloud/templates/sources.list.{distro}.deb822.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL_DEB822)
        cc_apt_configure.handle("test", {"apt_mirror": mirror}, mycloud, None)
        sources_file = tmpdir.join(f"/etc/apt/sources.list.d/{distro}.sources")
        assert (
            EXPECTED_CONVERTED_CONTENT_DEB822.replace(
                "http://archive.ubuntu.com/ubuntu/", mirror
            )
            == sources_file.read()
        )
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

    @staticmethod
    def myresolve(name):
        """Fake util.is_resolvable for mirrorfail tests"""
        if "does.not.exist" in name:
            print("Faking FAIL for '%s'" % name)
            return False
        else:
            print("Faking SUCCESS for '%s'" % name)
            return True

    @pytest.mark.parametrize(
        "distro,mirrorlist,mirrorcheck",
        (
            (
                "ubuntu",
                ["http://does.not.exist", "http://archive.ubuntu.com/ubuntu/"],
                "http://archive.ubuntu.com/ubuntu/",
            ),
            (
                "debian",
                [
                    "http://does.not.exist",
                    "http://httpredir.debian.org/debian/",
                ],
                "http://httpredir.debian.org/debian/",
            ),
        ),
    )
    def test_apt_v1_srcl_distro_mirrorfail(
        self, distro, mirrorlist, mirrorcheck, mocker, tmpdir
    ):
        """Test rendering of a source.list from template for each distro"""
        mycloud = get_cloud(distro)
        tmpl_file = f"/etc/cloud/templates/sources.list.{distro}.deb822.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL_DEB822)

        mockresolve = mocker.patch.object(
            util, "is_resolvable", side_effect=self.myresolve
        )
        cc_apt_configure.handle(
            "test", {"apt_mirror_search": mirrorlist}, mycloud, None
        )
        sources_file = tmpdir.join(f"/etc/apt/sources.list.d/{distro}.sources")
        assert (
            EXPECTED_CONVERTED_CONTENT_DEB822.replace(
                "http://archive.ubuntu.com/ubuntu/", mirrorcheck
            )
            == sources_file.read()
        )
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

        mockresolve.assert_any_call("http://does.not.exist")
        mockresolve.assert_any_call(mirrorcheck)

    @pytest.mark.parametrize(
        "deb822,cfg,apt_file,expected",
        (
            pytest.param(
                True,
                util.load_yaml(YAML_TEXT_CUSTOM_SL_DEB822),
                "/etc/apt/sources.list.d/ubuntu.sources",
                EXPECTED_CONVERTED_CONTENT_DEB822 + "# custom_sources_list\n",
                id="deb822_and_deb822_sources_list_writes_deb822_source_file",
            ),
            pytest.param(
                True,
                util.load_yaml(YAML_TEXT_CUSTOM_SL),
                "/etc/apt/sources.list",
                EXPECTED_CONVERTED_CONTENT + "# FIND_SOMETHING_SPECIAL\n",
                id="deb822_and_non_deb822_sources_list_writes_apt_list_file",
            ),
            pytest.param(
                False,
                util.load_yaml(YAML_TEXT_CUSTOM_SL),
                "/etc/apt/sources.list",
                EXPECTED_CONVERTED_CONTENT + "# FIND_SOMETHING_SPECIAL\n",
                id="nodeb822_and_nondeb822_sources_list_writes_list_file",
            ),
            pytest.param(
                True,
                util.load_yaml(YAML_TEXT_CUSTOM_SL_DEB822),
                "/etc/apt/sources.list.d/ubuntu.sources",
                EXPECTED_CONVERTED_CONTENT_DEB822 + "# custom_sources_list\n",
                id="nodeb822_and_deb822_sources_list_writes_sources_file",
            ),
        ),
    )
    def test_apt_v1_srcl_custom(
        self, deb822, cfg, apt_file, expected, mocker, tmpdir
    ):
        """Test rendering from a custom source.list template"""
        self.deb822 = mocker.patch.object(
            cc_apt_configure.features,
            "APT_DEB822_SOURCE_LIST_FILE",
            deb822,
        )
        mycloud = get_cloud("ubuntu")
        if deb822:
            tmpl_file = "/etc/cloud/templates/sources.list.ubuntu.deb822.tmpl"
            tmpl_content = EXAMPLE_TMPL_DEB822
        else:
            tmpl_content = EXAMPLE_TMPL
            tmpl_file = "/etc/cloud/templates/sources.list.ubuntu.tmpl"
        util.write_file(tmpl_file, tmpl_content)

        # the second mock restores the original subp
        cc_apt_configure.handle("notimportant", cfg, mycloud, None)
        sources_file = tmpdir.join(apt_file)
        assert expected == sources_file.read()
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)
