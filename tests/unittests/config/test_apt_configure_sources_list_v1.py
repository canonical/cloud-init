# This file is part of cloud-init. See LICENSE file for license information.

""" test_handler_apt_configure_sources_list
Test templating of sources list
"""
import stat

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from tests.unittests.util import get_cloud

EXAMPLE_TMPL = """\
## template:jinja
## Note, this file is written by cloud-init on first boot of an instance
## modifications made here will not survive a re-bundle.
## if you wish to make changes you can:
## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
##     or do the same in user-data
## b.) add sources in /etc/apt/sources.list.d
## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb {{mirror}} {{codename}} main restricted
deb-src {{mirror}} {{codename}} main restricted
"""

YAML_TEXT_CUSTOM_SL = """
apt_mirror: http://archive.ubuntu.com/ubuntu/
apt_custom_sources_list: |
    ## Note, this file is written by cloud-init on first boot of an instance
    ## modifications made here will not survive a re-bundle.
    ## if you wish to make changes you can:
    ## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
    ##     or do the same in user-data
    ## b.) add sources in /etc/apt/sources.list.d
    ## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

    # See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
    # newer versions of the distribution.
    deb $MIRROR $RELEASE main restricted
    deb-src $MIRROR $RELEASE main restricted
    # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = """## Note, this file is written by cloud-init on first boot of an instance
## modifications made here will not survive a re-bundle.
## if you wish to make changes you can:
## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
##     or do the same in user-data
## b.) add sources in /etc/apt/sources.list.d
## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
deb-src http://archive.ubuntu.com/ubuntu/ fakerelease main restricted
"""  # noqa: E501


@pytest.mark.usefixtures("fake_filesystem")
class TestAptSourceConfigSourceList:
    """TestAptSourceConfigSourceList
    Main Class to test sources list rendering
    """

    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        self.subp = mocker.patch.object(
            subp, "subp", return_value=("PPID   PID", "")
        )
        mocker.patch("cloudinit.config.cc_apt_configure._ensure_dependencies")
        lsb = mocker.patch("cloudinit.util.lsb_release")
        lsb.return_value = {"codename": "fakerelease"}
        m_arch = mocker.patch("cloudinit.util.get_dpkg_architecture")
        m_arch.return_value = "amd64"

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
        tmpl_file = f"/etc/cloud/templates/sources.list.{distro}.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL)
        cc_apt_configure.handle("test", {"apt_mirror": mirror}, mycloud, None)
        sources_file = tmpdir.join("/etc/apt/sources.list")
        assert (
            EXPECTED_CONVERTED_CONTENT.replace(
                "http://archive.ubuntu.com/ubuntu/", mirror
            )
            == sources_file.read()
        )
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

        self.subp.assert_called_once_with(
            ["ps", "-o", "ppid,pid", "-C", "dirmngr", "-C", "gpg-agent"],
            capture=True,
            target=None,
            rcs=[0, 1],
        )

    def test_apt_v1_source_list_ubuntu(self, tmpdir):
        """Test rendering of a source.list from template for ubuntu"""
        self.apt_source_list(
            "ubuntu", "http://archive.ubuntu.com/ubuntu/", tmpdir
        )
        self.subp.assert_called_once_with(
            ["ps", "-o", "ppid,pid", "-C", "dirmngr", "-C", "gpg-agent"],
            capture=True,
            target=None,
            rcs=[0, 1],
        )

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
        """Test rendering of a source.list from template for ubuntu"""
        mycloud = get_cloud(distro)
        tmpl_file = f"/etc/cloud/templates/sources.list.{distro}.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL)

        mockresolve = mocker.patch.object(
            util, "is_resolvable", side_effect=self.myresolve
        )
        cc_apt_configure.handle(
            "test", {"apt_mirror_search": mirrorlist}, mycloud, None
        )
        sources_file = tmpdir.join("/etc/apt/sources.list")
        assert (
            EXPECTED_CONVERTED_CONTENT.replace(
                "http://archive.ubuntu.com/ubuntu/", mirrorcheck
            )
            == sources_file.read()
        )
        assert 0o644 == stat.S_IMODE(sources_file.stat().mode)

        mockresolve.assert_any_call("http://does.not.exist")
        mockresolve.assert_any_call(mirrorcheck)
        self.subp.assert_called_once_with(
            ["ps", "-o", "ppid,pid", "-C", "dirmngr", "-C", "gpg-agent"],
            capture=True,
            target=None,
            rcs=[0, 1],
        )

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
    def test_apt_v1_srcl_custom(self, cfg, apt_file, expected, tmpdir):
        """Test rendering from a custom source.list template"""
        mycloud = get_cloud("ubuntu")
        tmpl_file = "/etc/cloud/templates/sources.list.ubuntu.tmpl"
        util.write_file(tmpl_file, EXAMPLE_TMPL)

        # the second mock restores the original subp
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
