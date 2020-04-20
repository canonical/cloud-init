"""Tests for tools/render-cloudcfg"""

import os
import sys

import pytest

from cloudinit import util

# TODO(Look to align with tools.render-cloudcfg or cloudinit.distos.OSFAMILIES)
DISTRO_VARIANTS = ["amazon", "arch", "centos", "debian", "fedora", "freebsd",
                   "netbsd", "openbsd", "rhel", "suse", "ubuntu", "unknown"]


class TestRenderCloudCfg:

    cmd = [sys.executable, os.path.realpath('tools/render-cloudcfg')]
    tmpl_path = os.path.realpath('config/cloud.cfg.tmpl')

    @pytest.mark.parametrize('variant', (DISTRO_VARIANTS))
    def test_variant_sets_distro_in_cloud_cfg(self, variant, tmpdir):
        outfile = tmpdir.join('outcfg').strpath
        util.subp(
            self.cmd + ['--variant', variant, self.tmpl_path, outfile])
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())
        if variant == 'unknown':
            variant = 'ubuntu'  # Unknown is defaulted to ubuntu
        assert system_cfg['system_info']['distro'] == variant

    @pytest.mark.parametrize('variant', (DISTRO_VARIANTS))
    def test_variant_sets_default_user_in_cloud_cfg(self, variant, tmpdir):
        outfile = tmpdir.join('outcfg').strpath
        util.subp(
            self.cmd + ['--variant', variant, self.tmpl_path, outfile])
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())

        default_user_exceptions = {
            'amazon': 'ec2-user', 'debian': 'ubuntu', 'unknown': 'ubuntu'}
        default_user = system_cfg['system_info']['default_user']['name']
        assert default_user == default_user_exceptions.get(variant, variant)

    @pytest.mark.parametrize('variant,renderers', (
        ('freebsd', ['freebsd']), ('netbsd', ['netbsd']),
        ('openbsd', ['openbsd']), ('ubuntu', ['netplan', 'eni', 'sysconfig']))
    )
    def test_variant_sets_network_renderer_priority_in_cloud_cfg(
        self, variant, renderers, tmpdir
    ):
        outfile = tmpdir.join('outcfg').strpath
        util.subp(
            self.cmd + ['--variant', variant, self.tmpl_path, outfile])
        with open(outfile) as stream:
            system_cfg = util.load_yaml(stream.read())

        assert renderers == system_cfg['system_info']['network']['renderers']
