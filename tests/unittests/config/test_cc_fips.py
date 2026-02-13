# This file is part of cloud-init. See LICENSE file for license information.
"""Tests for cc_fips module."""

from unittest import mock

import pytest

from cloudinit import distros, helpers
from cloudinit.config.cc_fips import (
    handle,
)
from cloudinit.config.schema import get_schema, validate_cloudconfig_schema
from tests.unittests.helpers import skipUnlessJsonSchema


@pytest.fixture
def dist():
    cls = distros.fetch("rhel")
    paths = helpers.Paths({})
    return cls("rhel", {}, paths)


class TestAppendCmdlineGrub:
    @mock.patch("cloudinit.distros.rhel.os.path.exists", return_value=True)
    @mock.patch("cloudinit.distros.rhel.subp.subp")
    @mock.patch("cloudinit.distros.rhel.util.write_file")
    @mock.patch("cloudinit.distros.rhel.util.load_text_file")
    def test_adds_to_both_vars(self, m_load, m_write, m_subp, m_exists, dist):
        content = (
            'GRUB_CMDLINE_LINUX="quiet"\n'
            'GRUB_CMDLINE_LINUX_DEFAULT="splash"\n'
        )
        m_load.return_value = content
        dist._append_cmdline_grub("fips=1")
        result = m_write.call_args[0][1]
        assert "fips=1" in result
        assert "quiet fips=1" in result or "fips=1" in result
        assert "splash fips=1" in result or "fips=1" in result

    @mock.patch("cloudinit.distros.rhel.os.path.exists", return_value=True)
    @mock.patch("cloudinit.distros.rhel.subp.subp")
    @mock.patch("cloudinit.distros.rhel.util.write_file")
    @mock.patch("cloudinit.distros.rhel.util.load_text_file")
    def test_idempotent_when_present(
        self, m_load, m_write, m_subp, m_exists, dist
    ):
        content = 'GRUB_CMDLINE_LINUX="quiet fips=1"\n'
        m_load.return_value = content
        dist._append_cmdline_grub("fips=1")
        m_write.assert_not_called()

    @mock.patch("cloudinit.distros.rhel.os.path.exists", return_value=True)
    @mock.patch("cloudinit.distros.rhel.subp.subp")
    @mock.patch("cloudinit.distros.rhel.util.write_file")
    @mock.patch("cloudinit.distros.rhel.util.load_text_file")
    def test_preserves_other_lines(
        self, m_load, m_write, m_subp, m_exists, dist
    ):
        content = '# Some comment\nGRUB_CMDLINE_LINUX="a=b"\n'
        m_load.return_value = content
        dist._append_cmdline_grub("fips=1")
        result = m_write.call_args[0][1]
        assert "# Some comment" in result
        assert "a=b fips=1" in result or "fips=1" in result


class TestHandle:
    def test_skips_when_fips_not_enabled(self, dist):
        dist.install_packages = mock.MagicMock()
        cfg = {"fips": False}
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", cfg, cloud, [])
        dist.install_packages.assert_not_called()

    def test_skips_when_no_fips_key(self, dist):
        dist.install_packages = mock.MagicMock()
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", {}, cloud, [])
        dist.install_packages.assert_not_called()

    @mock.patch(
        "cloudinit.config.cc_fips.util.fips_enabled", return_value=True
    )
    def test_skips_when_already_fips_enabled(self, m_fips, dist):
        dist.install_packages = mock.MagicMock()
        cfg = {"fips": True}
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", cfg, cloud, [])
        m_fips.assert_called_once()
        dist.install_packages.assert_not_called()

    @mock.patch(
        "cloudinit.config.cc_fips.util.fips_enabled", return_value=False
    )
    @mock.patch(
        "cloudinit.config.cc_fips.util.is_uki_system", return_value=True
    )
    def test_uki_calls_append_kernel_cmdline(self, m_uki, m_fips, dist):
        dist.append_kernel_cmdline = mock.MagicMock()
        cfg = {"fips": True}
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", cfg, cloud, [])
        dist.append_kernel_cmdline.assert_called_once_with("fips=1")

    @mock.patch("cloudinit.subp.subp")
    @mock.patch(
        "cloudinit.config.cc_fips.util.fips_enabled", return_value=False
    )
    @mock.patch(
        "cloudinit.config.cc_fips.util.is_uki_system", return_value=False
    )
    def test_grub_path_calls_grubby(self, m_uki, m_fips, m_subp, dist):
        dist.install_packages = mock.MagicMock()
        # First call: fips-mode-setup (fail); second call: grubby (succeed)
        m_subp.side_effect = [FileNotFoundError(), None]
        cfg = {"fips": True}
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", cfg, cloud, [])
        m_subp.assert_any_call(
            ["grubby", "--update-kernel=ALL", "--args=fips=1"]
        )

    @mock.patch("cloudinit.config.cc_fips.subp.subp")
    @mock.patch("cloudinit.distros.rhel.util.write_file")
    @mock.patch("cloudinit.distros.rhel.util.load_text_file")
    @mock.patch(
        "cloudinit.config.cc_fips.util.fips_enabled", return_value=False
    )
    @mock.patch(
        "cloudinit.config.cc_fips.util.is_uki_system", return_value=False
    )
    @mock.patch("cloudinit.distros.rhel.os.path.exists")
    def test_grub_fallback_edits_grub_default(
        self, m_exists, m_uki, m_fips, m_load, m_write, m_subp, dist
    ):
        # fips-mode-setup and grubby fail; /etc/default/grub exists so we edit
        grub_default = "/etc/default/grub"
        m_subp.side_effect = [
            FileNotFoundError(),  # fips-mode-setup
            FileNotFoundError(),  # grubby
            None,  # grub2-mkconfig
            None,  # dracut
        ]
        m_exists.side_effect = lambda p: p == grub_default
        m_load.return_value = 'GRUB_CMDLINE_LINUX="quiet"\n'
        cfg = {"fips": True}
        cloud = mock.MagicMock()
        cloud.distro = dist
        handle("fips", cfg, cloud, [])
        m_load.assert_called_with(grub_default)
        m_write.assert_called()
        subp_calls = [c[0][0] for c in m_subp.call_args_list if c[0]]
        assert any("grub2-mkconfig" in cmd for cmd in subp_calls)


class TestFipsSchema:
    @pytest.mark.parametrize(
        "config",
        (
            {"fips": True},
            {"fips": False},
        ),
    )
    @skipUnlessJsonSchema()
    def test_valid_config(self, config):
        schema = get_schema()
        validate_cloudconfig_schema(config, schema, strict=True)
