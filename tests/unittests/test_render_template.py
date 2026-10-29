"""Tests for tools/render-template"""

import shlex
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
            "azurelinux": "azureuser",
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


@pytest.mark.allow_subp_for(sys.executable, "sh")
class TestRenderCloudInitGenerator:
    tmpl_path = cloud_init_project_dir("systemd/cloud-init-generator.tmpl")

    @pytest.mark.parametrize("variant", DISTRO_VARIANTS)
    @pytest.mark.parametrize(
        "lib_exec_dir",
        [
            "/usr/libexec/cloud-init",
            "/usr/lib/cloud-init",
            "/opt/custom helpers/cloud-init",
        ],
    )
    def test_configured_helper_directory(
        self, tmp_path, variant, lib_exec_dir
    ):
        outfile = tmp_path / "cloud-init-generator"
        templater.render_template(
            variant,
            self.tmpl_path,
            str(outfile),
            is_yaml=False,
            lib_exec_dir=lib_exec_dir,
        )
        assert self.get_dsidentify(outfile.read_text()) == (
            lib_exec_dir + "/ds-identify"
        )

    @pytest.mark.parametrize(
        "variant,expected",
        [
            ("photon", "/usr/libexec/cloud-init/ds-identify"),
            ("fedora", "/usr/libexec/cloud-init/ds-identify"),
            ("ubuntu", "/usr/lib/cloud-init/ds-identify"),
            ("unknown", "/usr/lib/cloud-init/ds-identify"),
            ("benchmark", "/bin/true"),
        ],
    )
    def test_default_helper_directory(self, variant, expected):
        rendered = templater.render_string(
            util.load_text_file(self.tmpl_path), {"variant": variant}
        )
        assert self.get_dsidentify(rendered) == expected

    @pytest.mark.parametrize("lib_exec_dir", [None, "/opt/helpers/cloud-init"])
    def test_benchmark_ignores_helper_directory(self, tmp_path, lib_exec_dir):
        outfile = tmp_path / "cloud-init-generator"
        templater.render_template(
            "benchmark",
            self.tmpl_path,
            str(outfile),
            is_yaml=False,
            lib_exec_dir=lib_exec_dir,
        )
        assert self.get_dsidentify(outfile.read_text()) == "/bin/true"

    def test_helper_directory_cli(self, tmp_path):
        outfile = tmp_path / "cloud-init-generator"
        lib_exec_dir = "/opt/custom helpers/cloud-init"
        subp.subp(
            [
                sys.executable,
                cloud_init_project_dir("tools/render-template"),
                "--variant",
                "photon",
                "--lib-exec-dir",
                lib_exec_dir,
                self.tmpl_path,
                str(outfile),
            ]
        )
        assert self.get_dsidentify(outfile.read_text()) == (
            lib_exec_dir + "/ds-identify"
        )

    def test_generator_executes_helper_in_custom_directory(self, tmp_path):
        lib_exec_dir = tmp_path / "custom 'helpers' $dir `name` \\\"quoted\""
        lib_exec_dir.mkdir()
        helper = lib_exec_dir / "ds-identify"
        helper.write_text('#!/bin/sh\nprintf "helper executed\\n"\n')
        helper.chmod(0o755)
        outfile = tmp_path / "cloud-init-generator"
        templater.render_template(
            "photon",
            self.tmpl_path,
            str(outfile),
            is_yaml=False,
            lib_exec_dir=str(lib_exec_dir),
        )
        # Redirect runtime state into the temporary directory before running.
        rendered = outfile.read_text().replace(
            "/run/cloud-init", str(tmp_path / "run")
        )
        outfile.write_text(rendered)
        stdout, _ = subp.subp(
            ["sh", str(outfile)] + [str(tmp_path / "generator")] * 3
        )
        assert stdout == "helper executed\n"
        assert (tmp_path / "run" / "enabled").exists()
        assert (
            tmp_path / "generator/multi-user.target.wants/cloud-init.target"
        ).is_symlink()

    @staticmethod
    def get_dsidentify(rendered):
        assignment = next(
            line.strip()
            for line in rendered.splitlines()
            if line.strip().startswith("dsidentify=")
        )
        return shlex.split(assignment.split("=", 1)[1])[0]


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
