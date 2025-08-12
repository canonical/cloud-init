"""Tests for tools/render-template"""

import sys

import pytest

from cloudinit import subp, templater, util
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import skipUnlessJinjaVersionGreaterThan

# TODO(Look to align with tools.render-template or cloudinit.distos.OSFAMILIES)
DISTRO_VARIANTS = [
    "amazon",
    "arch",
    "azurelinux",
    "centos",
    "debian",
    "eurolinux",
    "fedora",
    "freebsd",
    "gentoo",
    "mariner",
    "netbsd",
    "openbsd",
    "photon",
    "raspberry-pi-os",
    "rhel",
    "suse",
    "ubuntu",
    "unknown",
]


@pytest.mark.allow_subp_for(sys.executable)
class TestRenderCloudCfg:
    cmd = [sys.executable, cloud_init_project_dir("tools/render-template")]
    tmpl_path = cloud_init_project_dir("config/cloud.cfg.tmpl")
    init_path = cloud_init_project_dir("sysvinit/freebsd/dsidentify.tmpl")

    def test_variant_sets_distro_in_cloud_cfg_subp(self, tmpdir):
        outfile = tmpdir.join("outcfg").strpath

        subp.subp(self.cmd + ["--variant", "ubuntu", self.tmpl_path, outfile])
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())
        assert system_cfg["system_info"]["distro"] == "ubuntu"

    def test_variant_sets_prefix_in_cloud_cfg_subp(self, tmpdir):
        outfile = tmpdir.join("outcfg").strpath

        subp.subp(
            self.cmd
            + [
                "--variant",
                "freebsd",
                "--prefix",
                "/usr/local",
                self.init_path,
                outfile,
            ]
        )
        with open(outfile) as stream:
            init_cfg = stream.readlines()
        assert 'command="/usr/local/lib/cloud-init/ds-identify"\n' in init_cfg

    @pytest.mark.parametrize("variant", (DISTRO_VARIANTS))
    def test_variant_sets_distro_in_cloud_cfg(self, variant, tmpdir):
        """Testing parametrized inputs with imported function saves ~0.5s per
        call versus calling as subp
        """
        outfile = tmpdir.join("outcfg").strpath

        templater.render_template(
            variant, self.tmpl_path, outfile, is_yaml=True
        )
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())
        if variant == "unknown":
            variant = "ubuntu"  # Unknown is defaulted to ubuntu
        assert system_cfg["system_info"]["distro"] == variant

    @pytest.mark.parametrize("variant", (DISTRO_VARIANTS))
    def test_variant_sets_default_user_in_cloud_cfg(self, variant, tmpdir):
        """Testing parametrized inputs with imported function saves ~0.5s per
        call versus calling as subp
        """
        outfile = tmpdir.join("outcfg").strpath
        templater.render_template(
            variant, self.tmpl_path, outfile, is_yaml=True
        )
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())

        default_user_exceptions = {
            "amazon": "ec2-user",
            "rhel": "cloud-user",
            "centos": "cloud-user",
            "raspberry-pi-os": "pi",
            "unknown": "ubuntu",
        }
        default_user = system_cfg["system_info"]["default_user"]["name"]
        assert default_user == default_user_exceptions.get(variant, variant)

    @pytest.mark.parametrize(
        "variant,renderers",
        (
            ("freebsd", ["freebsd"]),
            ("netbsd", ["netbsd"]),
            ("openbsd", ["openbsd"]),
            ("ubuntu", ["netplan", "eni", "sysconfig"]),
            ("raspberry-pi-os", ["netplan", "network-manager"]),
        ),
    )
    def test_variant_sets_network_renderer_priority_in_cloud_cfg(
        self, variant, renderers, tmpdir
    ):
        """Testing parametrized inputs with imported function saves ~0.5s per
        call versus calling as subp
        """
        outfile = tmpdir.join("outcfg").strpath
        templater.render_template(
            variant, self.tmpl_path, outfile, is_yaml=True
        )
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())

        assert renderers == system_cfg["system_info"]["network"]["renderers"]


EXPECTED_DEBIAN = """\
deb testmirror testcodename main
deb-src testmirror testcodename main
deb testsecurity testcodename-security main
deb-src testsecurity testcodename-security main
deb testmirror testcodename-updates main
deb-src testmirror testcodename-updates main
deb testmirror testcodename-backports main
deb-src testmirror testcodename-backports main
"""

EXPECTED_DEBIAN_DEB822 = """\
Types: deb deb-src
URIs: testmirror
Suites: testcodename testcodename-updates testcodename-backports
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Types: deb deb-src
URIs: testsecurity
Suites: testcodename-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
"""

EXPECTED_UBUNTU = """\
deb testmirror testcodename main restricted
deb testmirror testcodename-updates main restricted
deb testmirror testcodename universe
deb testmirror testcodename-updates universe
deb testmirror testcodename multiverse
deb testmirror testcodename-updates multiverse
deb testmirror testcodename-backports main restricted universe multiverse
deb testsecurity testcodename-security main restricted
deb testsecurity testcodename-security universe
deb testsecurity testcodename-security multiverse
"""

EXPECTED_UBUNTU_DEB822 = """\
Types: deb
URIs: testmirror
Suites: testcodename testcodename-updates testcodename-backports
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Types: deb
URIs: testsecurity
Suites: testcodename-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""


class TestRenderSourcesList:
    @pytest.mark.parametrize(
        "template_path,expected",
        [
            pytest.param(
                "templates/sources.list.debian.tmpl",
                EXPECTED_DEBIAN,
                id="debian",
            ),
            pytest.param(
                "templates/sources.list.debian.deb822.tmpl",
                EXPECTED_DEBIAN_DEB822,
                id="debian_822",
            ),
            pytest.param(
                "templates/sources.list.ubuntu.tmpl",
                EXPECTED_UBUNTU,
                id="ubuntu",
            ),
            pytest.param(
                "templates/sources.list.ubuntu.deb822.tmpl",
                EXPECTED_UBUNTU_DEB822,
                id="ubuntu_822",
            ),
        ],
    )
    @skipUnlessJinjaVersionGreaterThan((3, 0, 0))
    def test_render_sources_list_templates(
        self, tmpdir, template_path, expected
    ):
        params = {
            "mirror": "testmirror",
            "security": "testsecurity",
            "codename": "testcodename",
        }
        template_path = cloud_init_project_dir(template_path)
        rendered = templater.render_string(open(template_path).read(), params)
        filtered = "\n".join(
            line
            for line in rendered.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        assert filtered.strip() == expected.strip()
