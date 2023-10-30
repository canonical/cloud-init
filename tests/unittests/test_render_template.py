"""Tests for tools/render-template"""

import sys

import pytest

from cloudinit import subp, templater, util
from tests.unittests.helpers import cloud_init_project_dir

# TODO(Look to align with tools.render-template or cloudinit.distos.OSFAMILIES)
DISTRO_VARIANTS = [
    "amazon",
    "arch",
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
