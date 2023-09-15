# This file is part of cloud-init. See LICENSE file for license information.

""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import stat

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from cloudinit.distros.debian import Distro
from tests.unittests.util import get_cloud

TARGET = "/"

# Input and expected output for the custom template
EXAMPLE_TMPL = """\
## template:jinja
deb {{mirror}} {{codename}} main restricted
deb-src {{mirror}} {{codename}} main restricted
deb {{mirror}} {{codename}}-updates universe restricted
deb {{security}} {{codename}}-security multiverse
"""

YAML_TEXT_CUSTOM_SL = """
apt:
  primary:
    - arches: [default]
      uri: http://test.ubuntu.com/ubuntu/
  security:
    - arches: [default]
      uri: http://testsec.ubuntu.com/ubuntu/
  sources_list: |

      # Note, this file is written by cloud-init at install time.
      deb $MIRROR $RELEASE main restricted
      deb-src $MIRROR $RELEASE main restricted
      deb $PRIMARY $RELEASE universe restricted
      deb $SECURITY $RELEASE-security multiverse
      # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = """
# Note, this file is written by cloud-init at install time.
deb http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel universe restricted
deb http://testsec.ubuntu.com/ubuntu/ fakerel-security multiverse
"""

# mocked to be independent to the unittest system

EXPECTED_BASE_CONTENT = """\
deb http://archive.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://archive.ubuntu.com/ubuntu/ fakerel main restricted
deb http://archive.ubuntu.com/ubuntu/ fakerel-updates universe restricted
deb http://security.ubuntu.com/ubuntu/ fakerel-security multiverse
"""

EXPECTED_MIRROR_CONTENT = """\
deb http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel-updates main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel-security main restricted
"""

EXPECTED_PRIMSEC_CONTENT = """\
deb http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel-updates universe restricted
deb http://testsec.ubuntu.com/ubuntu/ fakerel-security multiverse
"""


@pytest.mark.usefixtures("fake_filesystem")
class TestAptSourceConfigSourceList:
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""

    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        self.subp = mocker.patch.object(
            subp,
            "subp",
            return_value=("PPID   PID", ""),
        )
        lsb = mocker.patch("cloudinit.util.lsb_release")
        lsb.return_value = {"codename": "fakerel"}
        m_arch = mocker.patch("cloudinit.util.get_dpkg_architecture")
        m_arch.return_value = "amd64"
        mocker.patch("cloudinit.config.cc_apt_configure._ensure_dependencies")

    @pytest.mark.parametrize(
        "distro,template_present",
        (("ubuntu", True), ("debian", True), ("rhel", False)),
    )
    def test_apt_v3_empty_cfg_source_list_by_distro(
        self, distro, template_present, mocker, tmpdir
    ):
        """Template based on distro, empty config relies on mirror default."""
        template = f"/etc/cloud/templates/sources.list.{distro}.tmpl"
        if template_present:
            util.write_file(template, EXAMPLE_TMPL)

        mycloud = get_cloud(distro)
        mock_shouldcfg = mocker.patch.object(
            cc_apt_configure,
            "_should_configure_on_empty_apt",
            return_value=(True, "test"),
        )
        cc_apt_configure.handle("test", {"apt": {}}, mycloud, None)

        sources_file = tmpdir.join("/etc/apt/sources.list")
        if template_present:
            assert EXPECTED_BASE_CONTENT == sources_file.read()
            assert 0o644 == stat.S_IMODE(sources_file.stat().mode)
        else:
            assert (
                sources_file.exists() is False
            ), f"Unexpected file found: {sources_file}"

        assert 1 == mock_shouldcfg.call_count

    def test_apt_v3_source_list_ubuntu_snappy(self, mocker):
        """test_apt_v3_source_list_ubuntu_snappy - without custom sources or
        parms"""
        cfg = {"apt": {}}
        mycloud = get_cloud()

        mock_writefile = mocker.patch.object(util, "write_file")
        mock_issnappy = mocker.patch.object(util, "system_is_snappy")
        mock_issnappy.return_value = True
        cc_apt_configure.handle("test", cfg, mycloud, None)
        mock_writefile.assert_not_called()
        assert 1 == mock_issnappy.call_count

    @pytest.mark.parametrize(
        "tmpl_file,tmpl_content,apt_file,expected",
        (
            (
                "/etc/cloud/templates/sources.list.ubuntu.tmpl",
                EXAMPLE_TMPL,
                "/etc/apt/sources.list",
                EXPECTED_PRIMSEC_CONTENT,
            ),
        ),
    )
    def test_apt_v3_source_list_psm(
        self, tmpl_file, tmpl_content, apt_file, expected, tmpdir
    ):
        """test_apt_v3_source_list_psm - Test specifying prim+sec mirrors"""
        pm = "http://test.ubuntu.com/ubuntu/"
        sm = "http://testsec.ubuntu.com/ubuntu/"
        cfg = {
            "preserve_sources_list": False,
            "primary": [{"arches": ["default"], "uri": pm}],
            "security": [{"arches": ["default"], "uri": sm}],
        }

        util.write_file(tmpl_file, tmpl_content)
        mycloud = get_cloud("ubuntu")
        cc_apt_configure.handle("test", {"apt": cfg}, mycloud, None)

        sources_file = tmpdir.join(apt_file)
        assert expected == sources_file.read()
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

    @pytest.mark.parametrize(
        "cfg,apt_file,expected",
        (
            pytest.param(
                util.load_yaml(YAML_TEXT_CUSTOM_SL),
                "/etc/apt/sources.list",
                EXPECTED_CONVERTED_CONTENT + "# FIND_SOMETHING_SPECIAL\n",
                id="sources_list_writes_list_file",
            ),
        ),
    )
    def test_apt_v3_srcl_custom(self, cfg, apt_file, expected, mocker, tmpdir):
        """test_apt_v3_srcl_custom - Test rendering a custom source template"""
        mycloud = get_cloud("debian")

        mocker.patch.object(Distro, "get_primary_arch", return_value="amd64")
        cc_apt_configure.handle("notimportant", cfg, mycloud, None)
        sources_file = tmpdir.join(apt_file)
        assert expected == sources_file.read()
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)
        self.subp.assert_called_once_with(
            ["ps", "-o", "ppid,pid", "-C", "dirmngr", "-C", "gpg-agent"],
            capture=True,
            target=None,
            rcs=[0, 1],
        )


# vi: ts=4 expandtab
